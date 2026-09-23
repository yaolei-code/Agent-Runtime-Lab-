from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class MemoryEntryRecord(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("mem"))
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    entry_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
