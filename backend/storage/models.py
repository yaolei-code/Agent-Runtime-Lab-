from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    tool_call_id: Mapped[str | None] = mapped_column(String(120))
    tool_name: Mapped[str | None] = mapped_column(String(120))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
