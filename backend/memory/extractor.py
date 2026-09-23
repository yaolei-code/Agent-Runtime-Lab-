from backend.memory.store import MemoryStore
from backend.runtime.events import TraceEventType
from backend.trace.store import TraceStore


class MemoryExtractor:
    def __init__(self, memory_store: MemoryStore, trace_store: TraceStore) -> None:
        self.memory_store = memory_store
        self.trace_store = trace_store

    def write_task_summary(self, run_id: str, user_input: str, answer: str | None) -> None:
        if not answer:
            return
        content = f"User asked: {user_input}\nAssistant answered: {answer}"
        entry = self.memory_store.add(
            memory_type="task_summary",
            content=content,
            source=f"run:{run_id}",
            metadata={"run_id": run_id},
        )
        self.trace_store.append(
            run_id,
            TraceEventType.MEMORY_WRITTEN.value,
            {"memory_id": entry.id, "type": entry.type},
        )
