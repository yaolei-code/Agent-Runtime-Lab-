"""Agent run 和对话消息的核心持久化记录。

runtime 在这里保存足够的状态，用于 run 完成后的检查，以及在不依赖内存中
Python 对象的情况下恢复因 approval 暂停的 run。
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base


def new_id(prefix: str) -> str:
    """创建带类型前缀的可读 ID，方便 UI 和日志追踪。"""

    return f"{prefix}_{uuid4().hex}"


class AgentRunRecord(Base):
    """一次用户触发的 Agent Run 的顶层生命周期记录。"""

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
    """持久化的 provider-style 对话消息。

    `raw` 保留原始 message 结构，包括 tool_calls 等字段。这样 runtime
    可以跨 loop iteration 和 approval resume 边界重建模型上下文。
    """

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
