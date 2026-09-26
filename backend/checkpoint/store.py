from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.checkpoint.models import RunCheckpointRecord
from backend.storage.models import new_id


SAFE_CHECKPOINT_KINDS = frozenset({"run_started", "before_llm", "after_tool"})


class CheckpointStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        run_id: str,
        *,
        step: int,
        kind: str,
        run_status: str,
        message_count: int,
        payload: dict[str, Any] | None = None,
    ) -> RunCheckpointRecord:
        current = self.session.scalar(
            select(func.max(RunCheckpointRecord.sequence)).where(RunCheckpointRecord.run_id == run_id)
        )
        checkpoint = RunCheckpointRecord(
            id=new_id("chk"),
            run_id=run_id,
            sequence=(current or 0) + 1,
            step=step,
            kind=kind,
            run_status=run_status,
            message_count=message_count,
            payload=payload or {},
        )
        self.session.add(checkpoint)
        self.session.flush()
        return checkpoint

    def latest_for_run(self, run_id: str) -> RunCheckpointRecord | None:
        return self.session.scalars(
            select(RunCheckpointRecord)
            .where(RunCheckpointRecord.run_id == run_id)
            .order_by(RunCheckpointRecord.sequence.desc())
        ).first()

    def latest_safe_for_run(self, run_id: str) -> RunCheckpointRecord | None:
        return self.session.scalars(
            select(RunCheckpointRecord)
            .where(
                RunCheckpointRecord.run_id == run_id,
                RunCheckpointRecord.kind.in_(SAFE_CHECKPOINT_KINDS),
            )
            .order_by(RunCheckpointRecord.sequence.desc())
        ).first()

    def list_for_run(self, run_id: str) -> list[RunCheckpointRecord]:
        return self.session.scalars(
            select(RunCheckpointRecord)
            .where(RunCheckpointRecord.run_id == run_id)
            .order_by(RunCheckpointRecord.sequence)
        ).all()
