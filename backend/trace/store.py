from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.trace.models import TraceEventRecord


class TraceStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        current = self.session.scalar(
            select(func.max(TraceEventRecord.sequence)).where(TraceEventRecord.run_id == run_id)
        )
        event = TraceEventRecord(
            run_id=run_id,
            type=event_type,
            payload=payload or {},
            sequence=(current or 0) + 1,
        )
        self.session.add(event)
        self.session.flush()

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        events = self.session.scalars(
            select(TraceEventRecord)
            .where(TraceEventRecord.run_id == run_id)
            .order_by(TraceEventRecord.sequence)
        ).all()
        return [
            {
                "event_id": event.id,
                "run_id": event.run_id,
                "type": event.type,
                "timestamp": event.timestamp.isoformat(),
                "payload": event.payload,
            }
            for event in events
        ]
