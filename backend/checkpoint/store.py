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

    def latest_compatible_safe_for_run(
        self,
        run_id: str,
        message_count: int,
    ) -> RunCheckpointRecord | None:
        """返回与当前持久化消息前缀一致的最新安全恢复点。

        V0.3 的 checkpoint 不包含完整 message snapshot，因此不能安全地把
        数据库回滚到任意历史位置。第一版恢复只接受消息数量完全一致的边界，
        避免名义上选择旧 checkpoint、实际上却用新状态继续执行。
        """

        return self.session.scalars(
            select(RunCheckpointRecord)
            .where(
                RunCheckpointRecord.run_id == run_id,
                RunCheckpointRecord.kind.in_(SAFE_CHECKPOINT_KINDS),
                RunCheckpointRecord.message_count == message_count,
            )
            .order_by(RunCheckpointRecord.sequence.desc())
        ).first()

    def list_for_run(self, run_id: str) -> list[RunCheckpointRecord]:
        return self.session.scalars(
            select(RunCheckpointRecord)
            .where(RunCheckpointRecord.run_id == run_id)
            .order_by(RunCheckpointRecord.sequence)
        ).all()
