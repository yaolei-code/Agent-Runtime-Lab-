from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.storage.database import Base
from backend.storage.models import new_id


class TraceEventRecord(Base):
    __tablename__ = "trace_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("evt"))
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
