"""Agent Runtime loop 和状态转换。

这个模块是 harness 核心。它负责围绕模型调用组织控制流：
构建 context、调用 provider、分发 action、评估 tool policy、为 approval 暂停、
执行工具、持久化状态，并记录 trace event。

供应商特定 response object、具体工具实现和数据库表细节都被隔离在协作者背后，
让 loop 保持可读、可测试。
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.approval.manager import ApprovalManager
from backend.checkpoint.store import CheckpointStore
from backend.conversation.store import ConversationStore
from backend.llm.base import LLMProvider, LLMProviderError
from backend.memory.extractor import MemoryExtractor
from backend.memory.retrieval import MemoryRetriever
from backend.runtime.actions import FinalAnswerAction, ToolCallAction
from backend.runtime.context import ContextBuilder
from backend.runtime.events import TraceEventType
from backend.runtime.state import AgentRunResult
from backend.runtime.status import RunStatus
from backend.storage.models import AgentRunRecord, MessageRecord, new_id
from backend.tools.executor import ToolExecutor
from backend.tools.execution_models import ToolExecutionStatus
from backend.tools.execution_store import ToolExecutionStore, UncertainToolExecutionError
from backend.tools.policy import PolicyDecisionType, ToolPolicy
from backend.tools.registry import ToolRegistry
from backend.trace.store import TraceStore


class AgentRuntime:
    """协调一次 Agent Run：从用户输入推进到最终答案或暂停。

    runtime 刻意只是编排者，而不是 god object：
    它决定何时调用 LLM、policy、tools、approval、trace 和 memory，
    但这些系统各自拥有自己的细节。
    """

    def __init__(
        self,
        session: Session,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        tool_policy: ToolPolicy,
        approval_manager: ApprovalManager,
        trace_store: TraceStore,
        checkpoint_store: CheckpointStore,
        conversation_store: ConversationStore,
        tool_execution_store: ToolExecutionStore,
        memory_retriever: MemoryRetriever,
        memory_extractor: MemoryExtractor,
        context_builder: ContextBuilder | None = None,
        max_steps: int = 8,
    ) -> None:
        """接收 runtime 的所有协作者。

        通过外部传入依赖，loop 可以很容易用 fake provider 和内存数据库测试，
        同时 runtime 不会绑定到某一个模型 SDK 或工具实现。
        """

        self.session = session
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.tool_policy = tool_policy
        self.approval_manager = approval_manager
        self.trace_store = trace_store
        self.checkpoint_store = checkpoint_store
        self.conversation_store = conversation_store
        self.tool_execution_store = tool_execution_store
        self.memory_retriever = memory_retriever
        self.memory_extractor = memory_extractor
        self.context_builder = context_builder or ContextBuilder()
        self.max_steps = max_steps

    def start(
        self,
        user_message: str,
        conversation_id: str | None = None,
    ) -> AgentRunResult:
        """创建持久化 run，并进入 Agent Loop。

        初始 run/message/trace 会在任何 LLM 工作前提交。这样即使 provider
        失败，也会留下可检查的 run 历史。
        """

        conversation = (
            self.conversation_store.require(conversation_id)
            if conversation_id
            else self.conversation_store.create(user_message)
        )
        self.conversation_store.touch(conversation)
        run = AgentRunRecord(
            id=new_id("run"),
            conversation_id=conversation.id,
            status=RunStatus.RUNNING.value,
            user_input=user_message,
            steps=0,
        )
        self.session.add(run)
        self._append_message(run.id, {"role": "user", "content": user_message})
        self.trace_store.append(
            run.id,
            TraceEventType.RUN_STARTED.value,
            {"user_input": user_message, "conversation_id": conversation.id},
        )
        self._checkpoint(run, "run_started", {"user_input": user_message})
        self.session.commit()
        return self._continue(run.id)

    def resume_run(self, run_id: str) -> AgentRunResult:
        """Manually resume a failed run from the latest safe checkpoint.

        V0.3 intentionally supports only explicit manual resume for failed runs.
        It does not infer stale running runs, scan on startup, or resume through
        approval boundaries.
        """

        run = self._require_run(run_id)
        if run.status == RunStatus.COMPLETED.value:
            raise ValueError("Completed runs cannot be resumed.")
        if run.status == RunStatus.WAITING_FOR_APPROVAL.value:
            raise ValueError("Run is waiting for approval. Use approval approve/reject API.")
        if run.status == RunStatus.RUNNING.value:
            raise ValueError("Running runs cannot be manually resumed in this version.")
        if run.status != RunStatus.FAILED.value:
            raise ValueError(f"Run status cannot be resumed: {run.status}")

        unresolved = self.tool_execution_store.unresolved_for_run(run.id)
        if unresolved:
            for execution in unresolved:
                if execution.status == ToolExecutionStatus.STARTED.value:
                    self.tool_execution_store.mark_unknown(execution)
                self.trace_store.append(
                    run.id,
                    TraceEventType.TOOL_EXECUTION_UNCERTAIN.value,
                    {
                        "tool_call_id": execution.tool_call_id,
                        "tool_name": execution.tool_name,
                    },
                )
            self.session.commit()
            raise ValueError(
                "Run contains a tool execution with an unknown outcome; automatic replay is unsafe."
            )

        checkpoint = self.checkpoint_store.latest_compatible_safe_for_run(
            run.id,
            self._message_count(run.id),
        )
        if checkpoint is None:
            if self.checkpoint_store.latest_safe_for_run(run.id) is None:
                raise ValueError("Run has no safe checkpoint to resume from.")
            raise ValueError("Run state has diverged from its safe checkpoint and cannot be resumed.")

        run.status = RunStatus.RUNNING.value
        run.answer = None
        self.trace_store.append(
            run.id,
            TraceEventType.RUN_RESUMED.value,
            {
                "checkpoint_id": checkpoint.id,
                "checkpoint_kind": checkpoint.kind,
                "checkpoint_sequence": checkpoint.sequence,
            },
        )
        self.session.commit()
        return self._continue(run.id)

    def resume_from_approval(self, approval_id: str, approved: bool) -> AgentRunResult:
        """恢复一个之前停在 APPROVAL_REQUIRED 的 run。

        approve 会执行原先请求的工具。reject 会写入一条 tool result，
        告诉模型人类拒绝了这次调用，然后 loop 继续。
        """

        approval = self.approval_manager.resolve(approval_id, approved)
        run = self._require_run(approval.run_id)
        run.status = RunStatus.RUNNING.value
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
            # approval 记录保存了原始 call_id/name/arguments，
            # 这是恢复执行所需的最小持久化状态。
            try:
                self._execute_tool_call(
                    run,
                    call_id=approval.tool_call_id,
                    tool_name=approval.tool_name,
                    arguments=approval.arguments,
                )
            except UncertainToolExecutionError as exc:
                return self._fail_run(run, str(exc))
        else:
            # reject 被建模为 tool response，这样下一轮 LLM 调用会像看到普通
            # tool result 一样看到这次拒绝。
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
        """主循环：context -> LLM action -> dispatch -> repeat or stop。"""

        run = self._require_run(run_id)

        # max_steps 是单次 start/resume 尝试的预算；run.steps 仍累计展示总步数。
        # 否则一个因 max_steps 失败的 run 在 resume 后会立即再次失败。
        steps_this_attempt = 0
        while steps_this_attempt < self.max_steps:
            steps_this_attempt += 1
            run.steps += 1
            # 每一轮都从持久化层重新加载 messages。这样跨 approval resume
            # 边界时，数据库就是上下文的事实来源。
            messages = self._load_context_messages(run)
            # 当前 retrieval 使用原始 user input。这样简单且可预测，
            # 但还不会根据中间 tool result 动态调整。
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
            self._checkpoint(
                run,
                "before_llm",
                {"message_count": len(messages), "tool_count": len(self.tool_registry.list_tools())},
            )

            try:
                # Provider adapter 返回内部 action，而不是 SDK object。
                # 这是保持 runtime provider-neutral 的关键边界。
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
            self._checkpoint(run, "after_llm", {"action": action.kind})

            if isinstance(action, FinalAnswerAction):
                return self._complete_run(run, action.content)

            if isinstance(action, ToolCallAction):
                result = self._handle_tool_call(run, action)
                if result is not None:
                    # 非 None 表示 run 需要有意停在这里；
                    # 当前主要是等待人工 approval。
                    return result
                continue

            return self._fail_run(run, "Unknown action returned by LLM provider.")

        return self._fail_run(run, f"Agent reached max_steps={self.max_steps}.")

    def _handle_tool_call(
        self,
        run: AgentRunRecord,
        action: ToolCallAction,
    ) -> AgentRunResult | None:
        """处理模型请求的工具调用。

        返回 None 表示 loop 应继续。返回 AgentRunResult 表示 run 必须立刻
        返回给调用方，例如进入 approval pause。
        """

        # provider 可能在恢复或重试后再次给出同一个 call_id。已经持久化的
        # assistant tool-call 不应重复追加，否则会形成无对应结果的消息。
        if not self._has_message(run.id, "assistant", action.call_id):
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
            # unknown tool 是可恢复的 agent 错误：把失败喂回对话，
            # 而不是让服务崩溃。
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
            # BLOCK 被表示成 tool failure，这样模型仍可生成最终回答，
            # 解释为什么动作被阻止。
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
            run.status = RunStatus.WAITING_FOR_APPROVAL.value
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
            self._checkpoint(
                run,
                "approval_pause",
                {
                    "approval_id": approval.id,
                    "tool_name": action.tool_name,
                    "risk_level": tool.risk_level.value,
                },
            )
            # 不在当前请求里等待。持久化暂停点，让 Approvals API 之后恢复 run。
            self.session.commit()
            return self._result(run, approval_id=approval.id)

        try:
            self._execute_tool_call(run, action.call_id, action.tool_name, action.arguments)
        except UncertainToolExecutionError as exc:
            return self._fail_run(run, str(exc))
        self.session.commit()
        return None

    def _execute_tool_call(
        self,
        run: AgentRunRecord,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """执行一个已批准/已允许的工具调用，并追加 tool message。"""

        existing = self.tool_execution_store.get(run.id, call_id)
        if existing is not None:
            if existing.tool_name != tool_name or existing.arguments != arguments:
                raise UncertainToolExecutionError(
                    f"Tool call {call_id} does not match its persisted execution record."
                )
            if existing.status != ToolExecutionStatus.COMPLETED.value:
                if existing.status == ToolExecutionStatus.STARTED.value:
                    self.tool_execution_store.mark_unknown(existing)
                self.trace_store.append(
                    run.id,
                    TraceEventType.TOOL_EXECUTION_UNCERTAIN.value,
                    {"tool_call_id": call_id, "tool_name": tool_name},
                )
                self.session.commit()
                raise UncertainToolExecutionError(
                    f"Tool execution outcome is unknown for call {call_id}; refusing to replay it."
                )

            result = self.tool_execution_store.to_result(existing)
            self.trace_store.append(
                run.id,
                TraceEventType.TOOL_RESULT_REUSED.value,
                {"tool_call_id": call_id, "tool_name": tool_name},
            )
            if not self._has_message(run.id, "tool", call_id):
                self._append_tool_result_message(run.id, call_id, tool_name, result.content)
                self._checkpoint(
                    run,
                    "after_tool",
                    {
                        "tool_call_id": call_id,
                        "tool_name": tool_name,
                        "ok": result.ok,
                        "reused": True,
                    },
                )
            return

        self.trace_store.append(
            run.id,
            TraceEventType.TOOL_STARTED.value,
            {"tool_call_id": call_id, "tool_name": tool_name},
        )
        execution = self.tool_execution_store.begin(run.id, call_id, tool_name, arguments)
        # 先提交执行意图，再进入不可与数据库事务绑定的外部副作用。
        self.session.commit()
        result = self.tool_executor.execute(tool_name, arguments)
        self.tool_execution_store.complete(execution, result)
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
        # tool result 必须作为 message 追加，并通过 tool_call_id 关联，
        # 这样下一轮 LLM 才能消费自己请求的结果。
        self._append_tool_result_message(run.id, call_id, tool_name, result.content)
        self._checkpoint(
            run,
            "after_tool",
            {
                "tool_call_id": call_id,
                "tool_name": tool_name,
                "ok": result.ok,
            },
        )

    def _complete_run(self, run: AgentRunRecord, answer: str) -> AgentRunResult:
        """持久化最终答案，并执行非关键路径的 memory extraction。"""

        self._append_message(run.id, {"role": "assistant", "content": answer})
        run.status = RunStatus.COMPLETED.value
        run.answer = answer
        self.trace_store.append(run.id, TraceEventType.RUN_COMPLETED.value, {"answer": answer})
        try:
            self.memory_extractor.write_task_summary(run.id, run.user_input, answer)
        except Exception as exc:
            # memory 写入有价值，但不应该在模型已经给出答案后，
            # 把一个已完成的用户任务变成失败 run。
            self.trace_store.append(
                run.id,
                TraceEventType.RUN_FAILED.value,
                {"non_fatal_memory_error": str(exc)},
            )
        self.session.commit()
        return self._result(run)

    def _fail_run(self, run: AgentRunRecord, message: str) -> AgentRunResult:
        """用统一结构持久化 fatal runtime/provider failure。"""

        run.status = RunStatus.FAILED.value
        run.answer = message
        self.trace_store.append(run.id, TraceEventType.RUN_FAILED.value, {"error": message})
        self._checkpoint(run, "run_failed", {"error": message})
        self.session.commit()
        return self._result(run)

    def _result(self, run: AgentRunRecord, approval_id: str | None = None) -> AgentRunResult:
        """构建返回给 API handler 的 runtime result。"""

        return AgentRunResult(
            conversation_id=run.conversation_id,
            run_id=run.id,
            status=run.status,
            answer=run.answer,
            approval_id=approval_id,
            trace=self.trace_store.list_for_run(run.id),
        )

    def _require_run(self, run_id: str) -> AgentRunRecord:
        """按 id 加载 run；不存在时抛出清晰的领域错误。"""

        run = self.session.get(AgentRunRecord, run_id)
        if run is None:
            raise KeyError(f"Unknown run: {run_id}")
        return run

    def _append_message(self, run_id: str, message: dict[str, Any]) -> None:
        """持久化一条对话消息，并保证 run 内顺序稳定。"""

        sequence = self.session.scalar(
            select(func.max(MessageRecord.sequence)).where(MessageRecord.run_id == run_id)
        )
        tool_call_id = message.get("tool_call_id")
        tool_name = message.get("name")
        if message.get("role") == "assistant" and message.get("tool_calls"):
            first_call = message["tool_calls"][0]
            tool_call_id = first_call.get("id")
            tool_name = first_call.get("function", {}).get("name")

        record = MessageRecord(
            id=new_id("msg"),
            run_id=run_id,
            role=message["role"],
            content=message.get("content"),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            # 保留 provider-style message 结构，包括 tool_calls，
            # 供后续重建上下文。
            raw=message,
            sequence=(sequence or 0) + 1,
        )
        self.session.add(record)
        self.session.flush()

    def _append_tool_result_message(
        self,
        run_id: str,
        call_id: str,
        tool_name: str,
        content: str,
    ) -> None:
        self._append_message(
            run_id,
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": content,
            },
        )

    def _has_message(self, run_id: str, role: str, tool_call_id: str) -> bool:
        return self.session.scalar(
            select(MessageRecord.id).where(
                MessageRecord.run_id == run_id,
                MessageRecord.role == role,
                MessageRecord.tool_call_id == tool_call_id,
            )
        ) is not None

    def _checkpoint(
        self,
        run: AgentRunRecord,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record a durable runtime boundary without changing control flow."""

        self.checkpoint_store.append(
            run.id,
            step=run.steps,
            kind=kind,
            run_status=run.status,
            message_count=self._message_count(run.id),
            payload=payload,
        )

    def _message_count(self, run_id: str) -> int:
        return self.session.scalar(
            select(func.count(MessageRecord.id)).where(MessageRecord.run_id == run_id)
        ) or 0

    def _load_messages(self, run_id: str) -> list[dict[str, Any]]:
        """为下一次 LLM 调用重建已持久化的对话历史。"""

        records = self.session.scalars(
            select(MessageRecord).where(MessageRecord.run_id == run_id).order_by(MessageRecord.sequence)
        ).all()
        return [record.raw or self._message_to_dict(record) for record in records]

    def _load_context_messages(self, run: AgentRunRecord) -> list[dict[str, Any]]:
        """加载当前 Run，以及同一 Conversation 中最近成功完成的历史。"""

        if not run.conversation_id:
            # 兼容 migration 前创建、尚未归属 Conversation 的历史 run。
            return self._load_messages(run.id)
        return self.conversation_store.context_messages(run.conversation_id, run.id)

    def _message_to_dict(self, record: MessageRecord) -> dict[str, Any]:
        """当 message row 没有 raw payload 时使用的兜底转换。"""

        message: dict[str, Any] = {"role": record.role, "content": record.content}
        if record.tool_call_id:
            message["tool_call_id"] = record.tool_call_id
        if record.tool_name:
            message["name"] = record.tool_name
        return message
