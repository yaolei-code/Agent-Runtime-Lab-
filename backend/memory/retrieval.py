from abc import ABC, abstractmethod

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.memory.models import MemoryEntryRecord
from backend.memory.store import MemoryStore


class MemoryRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, limit: int = 5) -> list[dict]:
        raise NotImplementedError


class SQLAlchemyMemoryRetriever(MemoryRetriever):
    """Portable retrieval boundary.

    This intentionally uses SQLAlchemy expressions instead of SQLite-specific APIs.
    A future SQLite FTS5 or PostgreSQL full-text implementation can be added behind
    the same MemoryRetriever interface.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve(self, query: str, limit: int = 5) -> list[dict]:
        terms = [term.strip() for term in query.split() if term.strip()]
        if not terms:
            return []

        clauses = []
        for term in terms[:6]:
            pattern = f"%{term}%"
            clauses.append(MemoryEntryRecord.content.ilike(pattern))
            clauses.append(MemoryEntryRecord.type.ilike(pattern))

        entries = self.session.scalars(
            select(MemoryEntryRecord)
            .where(or_(*clauses))
            .order_by(MemoryEntryRecord.created_at.desc())
            .limit(limit)
        ).all()
        store = MemoryStore(self.session)
        return [store._serialize(entry) for entry in entries]
