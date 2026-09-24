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
        self.memory_retriever = memory_retriever
        self.memory_extractor = memory_extractor
        self.context_builder = context_builder or ContextBuilder()
        self.max_steps = max_steps

    def start(self, user_message: str) -> AgentRunResult:
        """创建持久化 run，并进入 Agent Loop。

        初始 run/message/trace 会在任何 LLM 工作前提交。这样即使 provider
        失败，也会留下可检查的 run 历史。
        """

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
        """恢复一个之前停在 APPROVAL_REQUIRED 的 run。

        approve 会执行原先请求的工具。reject 会写入一条 tool result，
        告诉模型人类拒绝了这次调用，然后 loop 继续。
        """

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
            # approval 记录保存了原始 call_id/name/arguments，
            # 这是恢复执行所需的最小持久化状态。
            self._execute_tool_call(
                run,
                call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                arguments=approval.arguments,
            )
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

        while run.steps < self.max_steps:
            run.steps += 1
            # 每一轮都从持久化层重新加载 messages。这样跨 approval resume
            # 边界时，数据库就是上下文的事实来源。
            messages = self._load_messages(run.id)
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

        # 在执行工具/暂停决策前先保存 assistant tool-call message，
        # 这样下一次 provider 调用能重建准确的对话。
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
            # 不在当前请求里等待。持久化暂停点，让 Approvals API 之后恢复 run。
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
        """执行一个已批准/已允许的工具调用，并追加 tool message。"""

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
        # tool result 必须作为 message 追加，并通过 tool_call_id 关联，
        # 这样下一轮 LLM 才能消费自己请求的结果。
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
        """持久化最终答案，并执行非关键路径的 memory extraction。"""

        self._append_message(run.id, {"role": "assistant", "content": answer})
        run.status = "completed"
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

        run.status = "failed"
        run.answer = message
        self.trace_store.append(run.id, TraceEventType.RUN_FAILED.value, {"error": message})
        self.session.commit()
        return self._result(run)

    def _result(self, run: AgentRunRecord, approval_id: str | None = None) -> AgentRunResult:
        """构建返回给 API handler 的 runtime result。"""

        return AgentRunResult(
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
        record = MessageRecord(
            id=new_id("msg"),
            run_id=run_id,
            role=message["role"],
            content=message.get("content"),
            tool_call_id=message.get("tool_call_id"),
            tool_name=message.get("name"),
            # 保留 provider-style message 结构，包括 tool_calls，
            # 供后续重建上下文。
            raw=message,
            sequence=(sequence or 0) + 1,
        )
        self.session.add(record)
        self.session.flush()

    def _load_messages(self, run_id: str) -> list[dict[str, Any]]:
        """为下一次 LLM 调用重建已持久化的对话历史。"""

        records = self.session.scalars(
            select(MessageRecord).where(MessageRecord.run_id == run_id).order_by(MessageRecord.sequence)
        ).all()
        return [record.raw or self._message_to_dict(record) for record in records]

    def _message_to_dict(self, record: MessageRecord) -> dict[str, Any]:
        """当 message row 没有 raw payload 时使用的兜底转换。"""

        message: dict[str, Any] = {"role": record.role, "content": record.content}
        if record.tool_call_id:
            message["tool_call_id"] = record.tool_call_id
        if record.tool_name:
            message["name"] = record.tool_name
        return message
