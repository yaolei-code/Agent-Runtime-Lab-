"""Run management API。

这些接口不启动新的 Agent 行为，只读取已经持久化的 run 状态。
它们让前端可以展示历史执行记录，并为后续 checkpoint/recovery 能力打基础。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.approval.models import PendingApprovalRecord
from backend.storage.database import get_session
from backend.storage.models import AgentRunRecord

router = APIRouter(prefix="/runs", tags=["runs"])


class RunSummary(BaseModel):
    run_id: str
    status: str
    user_input: str
    answer: str | None
    steps: int
    created_at: datetime
    updated_at: datetime


class RunDetail(RunSummary):
    pending_approval: dict[str, Any] | None = None


def serialize_run(run: AgentRunRecord) -> RunSummary:
    """把 ORM run 转成 API 响应对象，避免把数据库对象直接暴露给前端。"""

    return RunSummary(
        run_id=run.id,
        status=run.status,
        user_input=run.user_input,
        answer=run.answer,
        steps=run.steps,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("", response_model=list[RunSummary])
def list_runs(
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[RunSummary]:
    """列出最近的 Agent Runs。

    limit 做一个简单上限，避免控制台第一次打开时拉取过多历史记录。
    """

    safe_limit = max(1, min(limit, 100))
    runs = session.scalars(
        select(AgentRunRecord)
        .order_by(AgentRunRecord.created_at.desc())
        .limit(safe_limit)
    ).all()
    return [serialize_run(run) for run in runs]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunDetail:
    """读取单个 run 的详情。

    如果 run 正在等待 approval，会附带当前 pending approval 的最小信息，
    方便前端把 run 状态和审批入口关联起来。
    """

    run = session.get(AgentRunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    pending = session.scalars(
        select(PendingApprovalRecord)
        .where(
            PendingApprovalRecord.run_id == run_id,
            PendingApprovalRecord.status == "pending",
        )
        .order_by(PendingApprovalRecord.created_at.asc())
    ).first()

    summary = serialize_run(run)
    return RunDetail(
        **summary.model_dump(),
        pending_approval=(
            {
                "approval_id": pending.id,
                "tool_name": pending.tool_name,
                "arguments": pending.arguments,
                "risk_level": pending.risk_level,
                "reason": pending.reason,
            }
            if pending
            else None
        ),
    )
