from backend.memory.retrieval import SQLAlchemyMemoryRetriever
from backend.memory.store import MemoryStore


def test_memory_write_read_delete(db_session):
    store = MemoryStore(db_session)
    entry = store.add("project_fact", "This project uses SQLAlchemy.", "test")
    db_session.commit()

    items = store.list()
    assert items[0]["id"] == entry.id
    assert store.delete(entry.id) is True
    db_session.commit()
    assert store.list() == []


def test_memory_retrieval(db_session):
    store = MemoryStore(db_session)
    store.add("decision", "Use Alembic for migrations.", "test")
    db_session.commit()

    results = SQLAlchemyMemoryRetriever(db_session).retrieve("Alembic")

    assert len(results) == 1
    assert results[0]["type"] == "decision"
