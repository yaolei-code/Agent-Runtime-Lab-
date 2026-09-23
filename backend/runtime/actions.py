from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class FinalAnswerAction:
    kind: Literal["final_answer"]
    content: str


@dataclass(frozen=True)
class ToolCallAction:
    kind: Literal["tool_call"]
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    assistant_message: dict[str, Any]


AgentAction = FinalAnswerAction | ToolCallAction
