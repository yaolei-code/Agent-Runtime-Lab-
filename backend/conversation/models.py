"""跨多个 Agent Run 持续存在的 Conversation 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class ConversationRecord(Base):
    """一段可连续追问的用户对话。"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("conv"))
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        index=True,
    )
