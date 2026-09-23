from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    status: str
    answer: str | None
    approval_id: str | None
    trace: list[dict[str, Any]]
