"""Tool execution ledger 的查询和状态转换。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.tools.base import ToolResult
from backend.tools.execution_models import ToolExecutionRecord, ToolExecutionStatus


class UncertainToolExecutionError(RuntimeError):
    """工具可能已产生副作用，但数据库没有可靠结果。"""


class ToolExecutionStore:
    """保存工具执行意图和结果，防止恢复时盲目重复副作用。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: str, tool_call_id: str) -> ToolExecutionRecord | None:
        return self.session.scalar(
            select(ToolExecutionRecord).where(
                ToolExecutionRecord.run_id == run_id,
                ToolExecutionRecord.tool_call_id == tool_call_id,
            )
        )

    def begin(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionRecord:
        """记录即将发生的外部调用；调用方必须在执行 Tool 前提交。"""

        existing = self.get(run_id, tool_call_id)
        if existing is not None:
            return existing

        execution = ToolExecutionRecord(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            status=ToolExecutionStatus.STARTED.value,
        )
        self.session.add(execution)
        self.session.flush()
        return execution

    def complete(self, execution: ToolExecutionRecord, result: ToolResult) -> None:
        execution.status = ToolExecutionStatus.COMPLETED.value
        execution.ok = result.ok
        execution.result_content = result.content
        execution.result_data = result.data
        execution.error = result.error
        self.session.flush()

    def mark_unknown(self, execution: ToolExecutionRecord) -> None:
        execution.status = ToolExecutionStatus.UNKNOWN.value
        self.session.flush()

    def unresolved_for_run(self, run_id: str) -> list[ToolExecutionRecord]:
        return self.session.scalars(
            select(ToolExecutionRecord).where(
                ToolExecutionRecord.run_id == run_id,
                ToolExecutionRecord.status.in_(
                    {ToolExecutionStatus.STARTED.value, ToolExecutionStatus.UNKNOWN.value}
                ),
            )
        ).all()

    @staticmethod
    def to_result(execution: ToolExecutionRecord) -> ToolResult:
        if execution.status != ToolExecutionStatus.COMPLETED.value:
            raise ValueError("Tool execution has no reusable result.")
        return ToolResult(
            ok=bool(execution.ok),
            content=execution.result_content or "",
            data=execution.result_data,
            error=execution.error,
        )
