"""Tool 调用执行状态的持久化模型。

Checkpoint 只能说明 Agent Loop 走到了哪里，不能证明一个有副作用的工具
是否已经实际执行。该表以 provider 的 tool_call_id 记录执行意图和结果，
为恢复流程提供“可以复用结果”或“结果不确定，禁止重放”的判断依据。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class ToolExecutionStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class ToolExecutionRecord(Base):
    """一次确定的 Tool Call 的执行凭据。"""

    __tablename__ = "tool_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "tool_call_id", name="uq_tool_executions_run_call"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("tex"))
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    ok: Mapped[bool | None] = mapped_column(Boolean)
    result_content: Mapped[str | None] = mapped_column(Text)
    result_data: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
