from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.approval.manager import ApprovalManager
from backend.llm.base import LLMProvider, LLMProviderError
from backend.memory.extractor import MemoryExtractor
from backend.memory.retrieval import MemoryRetriever
from backend.runtime.actions import FinalAnswerAction, ToolCallAction
from backend.runtime.context import ContextBuilder
from backend.runtime.events import TraceEventType
from backend.runtime.state import AgentRunResult
from backend.storage.models import AgentRunRecord, MessageRecord, new_id
from backend.tools.executor import ToolExecutor
from backend.tools.policy import PolicyDecisionType, ToolPolicy
from backend.tools.registry import ToolRegistry
from backend.trace.store import TraceStore


class AgentRuntime:
    def __init__(
        self,
        session: Session,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        tool_policy: ToolPolicy,
        approval_manager: ApprovalManager,
        trace_store: TraceStore,
        memory_retriever: MemoryRetriever,
        memory_extractor: MemoryExtractor,
        context_builder: ContextBuilder | None = None,
        max_steps: int = 8,
    ) -> None:
        self.session = session
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.tool_policy = tool_policy
        self.approval_manager = approval_manager
        self.trace_store = trace_store
        self.memory_retriever = memory_retriever
        self.memory_extractor = memory_extractor
        self.context_builder = context_builder or ContextBuilder()
        self.max_steps = max_steps

    def start(self, user_message: str) -> AgentRunResult:
        run = AgentRunRecord(
            id=new_id("run"),
            status="running",
            user_input=user_message,
            steps=0,
        )
        self.session.add(run)
        self._append_message(run.id, {"role": "user", "content": user_message})
        self.trace_store.append(
            run.id,
            TraceEventType.RUN_STARTED.value,
            {"user_input": user_message},
        )
        self.session.commit()
        return self._continue(run.id)

    def resume_from_approval(self, approval_id: str, approved: bool) -> AgentRunResult:
        approval = self.approval_manager.resolve(approval_id, approved)
        run = self._require_run(approval.run_id)
        run.status = "running"
        self.trace_store.append(
            run.id,
            TraceEventType.APPROVAL_RESOLVED.value,
            {
                "approval_id": approval.id,
                "status": approval.status,
                "tool_name": approval.tool_name,
            },
        )

        if approved:
            self._execute_tool_call(
                run,
                call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                arguments=approval.arguments,
            )
        else:
            self._append_message(
                run.id,
                {
                    "role": "tool",
                    "tool_call_id": approval.tool_call_id,
                    "name": approval.tool_name,
                    "content": "Approval rejected by human.",
                },
            )

        self.session.commit()
        return self._continue(run.id)

    def _continue(self, run_id: str) -> AgentRunResult:
        run = self._require_run(run_id)

        while run.steps < self.max_steps:
            run.steps += 1
            messages = self._load_messages(run.id)
            memories = self.memory_retriever.retrieve(run.user_input)
            self.trace_store.append(
                run.id,
                TraceEventType.MEMORY_RETRIEVED.value,
                {"count": len(memories), "memory_ids": [item["id"] for item in memories]},
            )
            context = self.context_builder.build(messages, memories)

            self.trace_store.append(
                run.id,
                TraceEventType.LLM_REQUEST.value,
                {"message_count": len(context), "tool_count": len(self.tool_registry.list_tools())},
            )

            try:
                action = self.llm_provider.complete(
                    messages=context,
                    tools=self.tool_registry.schemas_for_llm(),
                )
            except LLMProviderError as exc:
                return self._fail_run(run, f"LLM provider error: {exc}")
            except Exception as exc:
                return self._fail_run(run, f"Unexpected LLM error: {exc}")

            self.trace_store.append(
                run.id,
                TraceEventType.LLM_RESPONSE.value,
                {"action": action.kind},
            )

            if isinstance(action, FinalAnswerAction):
                return self._complete_run(run, action.content)

            if isinstance(action, ToolCallAction):
                result = self._handle_tool_call(run, action)
                if result is not None:
                    return result
                continue

            return self._fail_run(run, "Unknown action returned by LLM provider.")

        return self._fail_run(run, f"Agent reached max_steps={self.max_steps}.")

    def _handle_tool_call(
        self,
        run: AgentRunRecord,
        action: ToolCallAction,
    ) -> AgentRunResult | None:
        self._append_message(run.id, action.assistant_message)
        self.trace_store.append(
            run.id,
            TraceEventType.TOOL_REQUESTED.value,
            {
                "tool_call_id": action.call_id,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
            },
        )

        tool = self.tool_registry.get(action.tool_name)
        if tool is None:
            self._append_message(
                run.id,
                {
                    "role": "tool",
                    "tool_call_id": action.call_id,
                    "name": action.tool_name,
                    "content": f"Unknown tool: {action.tool_name}",
                },
            )
            self.trace_store.append(
                run.id,
                TraceEventType.TOOL_FAILED.value,
                {"tool_name": action.tool_name, "error": "unknown_tool"},
            )
            self.session.commit()
            return None

        decision = self.tool_policy.evaluate(tool)
        if decision.decision == PolicyDecisionType.BLOCK:
            self._append_message(
                run.id,
                {
                    "role": "tool",
                    "tool_call_id": action.call_id,
                    "name": action.tool_name,
                    "content": f"Tool blocked by policy: {decision.reason}",
                },
            )
            self.trace_store.append(
                run.id,
                TraceEventType.TOOL_FAILED.value,
                {"tool_name": action.tool_name, "policy": "block", "reason": decision.reason},
            )
            self.session.commit()
            return None

        if decision.decision == PolicyDecisionType.APPROVAL_REQUIRED:
            approval = self.approval_manager.create(run.id, action, tool, decision)
            run.status = "waiting_for_approval"
            self.trace_store.append(
                run.id,
                TraceEventType.APPROVAL_REQUESTED.value,
                {
                    "approval_id": approval.id,
                    "tool_name": action.tool_name,
                    "arguments": action.arguments,
                    "risk_level": tool.risk_level.value,
                    "reason": decision.reason,
                },
            )
            self.session.commit()
            return self._result(run, approval_id=approval.id)

        self._execute_tool_call(run, action.call_id, action.tool_name, action.arguments)
        self.session.commit()
        return None

    def _execute_tool_call(
        self,
        run: AgentRunRecord,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        self.trace_store.append(
            run.id,
            TraceEventType.TOOL_STARTED.value,
            {"tool_call_id": call_id, "tool_name": tool_name},
        )
        result = self.tool_executor.execute(tool_name, arguments)
        event_type = TraceEventType.TOOL_COMPLETED if result.ok else TraceEventType.TOOL_FAILED
        self.trace_store.append(
            run.id,
            event_type.value,
            {
                "tool_call_id": call_id,
                "tool_name": tool_name,
                "ok": result.ok,
                "result": result.data,
                "error": result.error,
            },
        )
        self._append_message(
            run.id,
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": result.content,
            },
        )

    def _complete_run(self, run: AgentRunRecord, answer: str) -> AgentRunResult:
        self._append_message(run.id, {"role": "assistant", "content": answer})
        run.status = "completed"
        run.answer = answer
        self.trace_store.append(run.id, TraceEventType.RUN_COMPLETED.value, {"answer": answer})
        try:
            self.memory_extractor.write_task_summary(run.id, run.user_input, answer)
        except Exception as exc:
            self.trace_store.append(
                run.id,
                TraceEventType.RUN_FAILED.value,
                {"non_fatal_memory_error": str(exc)},
            )
        self.session.commit()
        return self._result(run)

    def _fail_run(self, run: AgentRunRecord, message: str) -> AgentRunResult:
        run.status = "failed"
        run.answer = message
        self.trace_store.append(run.id, TraceEventType.RUN_FAILED.value, {"error": message})
        self.session.commit()
        return self._result(run)

    def _result(self, run: AgentRunRecord, approval_id: str | None = None) -> AgentRunResult:
        return AgentRunResult(
            run_id=run.id,
            status=run.status,
            answer=run.answer,
            approval_id=approval_id,
            trace=self.trace_store.list_for_run(run.id),
        )

    def _require_run(self, run_id: str) -> AgentRunRecord:
        run = self.session.get(AgentRunRecord, run_id)
        if run is None:
            raise KeyError(f"Unknown run: {run_id}")
        return run

    def _append_message(self, run_id: str, message: dict[str, Any]) -> None:
        sequence = self.session.scalar(
            select(func.max(MessageRecord.sequence)).where(MessageRecord.run_id == run_id)
        )
        record = MessageRecord(
            id=new_id("msg"),
            run_id=run_id,
            role=message["role"],
            content=message.get("content"),
            tool_call_id=message.get("tool_call_id"),
            tool_name=message.get("name"),
            raw=message,
            sequence=(sequence or 0) + 1,
        )
        self.session.add(record)
        self.session.flush()

    def _load_messages(self, run_id: str) -> list[dict[str, Any]]:
        records = self.session.scalars(
            select(MessageRecord).where(MessageRecord.run_id == run_id).order_by(MessageRecord.sequence)
        ).all()
        return [record.raw or self._message_to_dict(record) for record in records]

    def _message_to_dict(self, record: MessageRecord) -> dict[str, Any]:
        message: dict[str, Any] = {"role": record.role, "content": record.content}
        if record.tool_call_id:
            message["tool_call_id"] = record.tool_call_id
        if record.tool_name:
            message["name"] = record.tool_name
        return message
