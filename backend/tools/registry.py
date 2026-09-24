"""当前 runtime 可用工具的注册表。"""

from backend.tools.base import Tool


class ToolRegistry:
    """把工具发现和工具执行分开。

    registry 只回答“有哪些工具？”和“LLM 应该看到什么 schema？”。
    真正运行工具由 ToolExecutor 负责。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具，并在名称重复时尽早失败。"""

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def require(self, name: str) -> Tool:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {name}")
        return tool

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas_for_llm(self) -> list[dict]:
        """返回 provider adapter 期望格式的工具 schema。"""

        return [tool.schema_for_llm() for tool in self._tools.values()]

    def public_tools(self) -> list[dict]:
        return [tool.public_info() for tool in self._tools.values()]
