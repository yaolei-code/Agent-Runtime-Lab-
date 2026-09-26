from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class RunCheckpointRecord(Base):
    """A durable recovery boundary recorded during an Agent Run."""

    __tablename__ = "run_checkpoints"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("chk"))
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    run_status: Mapped[str] = mapped_column(String(40), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
