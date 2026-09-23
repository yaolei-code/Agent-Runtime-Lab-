from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    EXECUTE = "execute"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str
    data: Any = None
    error: str | None = None


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: RiskLevel

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def schema_for_llm(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def public_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level.value,
        }
