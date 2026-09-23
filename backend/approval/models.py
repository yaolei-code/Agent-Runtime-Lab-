from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class PendingApprovalRecord(Base):
    __tablename__ = "pending_approvals"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("appr"))
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assistant_message: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
