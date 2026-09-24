"""Human-in-the-loop approval 的持久化辅助模块。"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.approval.models import PendingApprovalRecord
from backend.runtime.actions import ToolCallAction
from backend.tools.base import Tool
from backend.tools.policy import PolicyDecision


class ApprovalManager:
    """创建和解决 approval 记录。

    Approval 不只是 UI flag。持久化记录里保存了足够的 tool-call 数据，
    让 AgentRuntime.resume_from_approval() 可以在创建 approval 的 HTTP
    请求早已返回之后，继续原来的 run。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        run_id: str,
        action: ToolCallAction,
        tool: Tool,
        decision: PolicyDecision,
    ) -> PendingApprovalRecord:
        """为被 policy 拦下的工具调用持久化一个 pending approval。"""

        approval = PendingApprovalRecord(
            run_id=run_id,
            tool_call_id=action.call_id,
            tool_name=action.tool_name,
            arguments=action.arguments,
            assistant_message=action.assistant_message,
            risk_level=tool.risk_level.value,
            reason=decision.reason,
            status="pending",
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def list_pending(self) -> list[dict[str, Any]]:
        """返回 control-plane UI 需要展示的 pending approval。"""

        approvals = self.session.scalars(
            select(PendingApprovalRecord)
            .where(PendingApprovalRecord.status == "pending")
            .order_by(PendingApprovalRecord.created_at.asc())
        ).all()
        return [self.serialize(item) for item in approvals]

    def resolve(self, approval_id: str, approved: bool) -> PendingApprovalRecord:
        """把 approval 标记为 approved/rejected，且只能解决一次。"""

        approval = self.session.get(PendingApprovalRecord, approval_id)
        if approval is None:
            raise KeyError(f"Unknown approval: {approval_id}")
        if approval.status != "pending":
            raise ValueError(f"Approval is already resolved: {approval.status}")
        approval.status = "approved" if approved else "rejected"
        approval.resolved_at = datetime.utcnow()
        self.session.flush()
        return approval

    def serialize(self, approval: PendingApprovalRecord) -> dict[str, Any]:
        """把 ORM 状态转换成 API 友好的 approval 数据。"""

        return {
            "approval_id": approval.id,
            "run_id": approval.run_id,
            "tool_call": {
                "id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "arguments": approval.arguments,
            },
            "risk": {
                "risk_level": approval.risk_level,
                "reason": approval.reason,
            },
            "status": approval.status,
            "created_at": approval.created_at.isoformat(),
            "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        }
