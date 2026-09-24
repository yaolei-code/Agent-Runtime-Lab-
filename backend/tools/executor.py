"""已注册工具的安全执行包装器。"""

from typing import Any

from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry


class ToolExecutor:
    """运行工具，并把工具失败转换成 ToolResult。

    这样工具异常不会直接打崩 HTTP 请求。runtime 可以把失败结果喂回 LLM，
    或者记录到 trace 中。
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """用模型提供的参数执行一个具名工具。"""

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
            # 工具错误是 agent loop 的数据，不是进程级错误。
            return ToolResult(ok=False, content=f"Tool error: {exc}", error=str(exc))
