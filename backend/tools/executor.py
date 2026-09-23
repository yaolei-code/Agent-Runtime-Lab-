from typing import Any

from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                ok=False,
                content=f"Unknown tool: {tool_name}",
                error=f"Unknown tool: {tool_name}",
            )

        if not isinstance(arguments, dict):
            return ToolResult(
                ok=False,
                content="Tool arguments must be an object.",
                error="Tool arguments must be an object.",
            )

        try:
            return tool.execute(arguments)
        except Exception as exc:
            return ToolResult(ok=False, content=f"Tool error: {exc}", error=str(exc))
