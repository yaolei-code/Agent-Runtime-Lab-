"""Harness 内部共享的工具契约。

工具是模型选择的 action 真正变成确定性代码执行的地方。
runtime 通过这个统一接口看待所有工具，因此 policy、execution 和 LLM schema
生成对内置工具和未来工具都保持一致。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """工具运行前供 policy 判断的风险类别。"""

    READ_ONLY = "read_only"
    WRITE = "write"
    EXECUTE = "execute"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


@dataclass(frozen=True)
class ToolResult:
    """工具执行后返回给 runtime 的结构化结果。"""

    ok: bool
    content: str
    data: Any = None
    error: str | None = None


class Tool(ABC):
    """每个工具都必须实现的基础接口。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: RiskLevel

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def schema_for_llm(self) -> dict[str, Any]:
        """用 OpenAI-compatible function schema 暴露工具。"""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def public_info(self) -> dict[str, Any]:
        """返回 Tools 页面/API 可展示的非敏感元数据。"""

        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level.value,
        }
