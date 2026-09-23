from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.memory.models import MemoryEntryRecord


class MemoryStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        memory_type: str,
        content: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntryRecord:
        entry = MemoryEntryRecord(
            type=memory_type,
            content=content,
            source=source,
            entry_metadata=metadata or {},
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def list(self) -> list[dict[str, Any]]:
        entries = self.session.scalars(
            select(MemoryEntryRecord).order_by(MemoryEntryRecord.created_at.desc())
        ).all()
        return [self._serialize(entry) for entry in entries]

    def delete(self, memory_id: str) -> bool:
        entry = self.session.get(MemoryEntryRecord, memory_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self.session.flush()
        return True

    def _serialize(self, entry: MemoryEntryRecord) -> dict[str, Any]:
        return {
            "id": entry.id,
            "type": entry.type,
            "content": entry.content,
            "source": entry.source,
            "metadata": entry.entry_metadata or {},
            "created_at": entry.created_at.isoformat(),
        }
