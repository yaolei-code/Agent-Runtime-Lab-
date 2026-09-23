from pathlib import Path
from typing import Any

from backend.tools.base import RiskLevel, Tool, ToolResult


class WorkspacePathGuard:
    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()

    def resolve(self, user_path: str) -> Path:
        if not isinstance(user_path, str) or not user_path.strip():
            raise ValueError("path must be a non-empty string.")
        requested = (self.workspace_dir / user_path).resolve()
        if requested != self.workspace_dir and self.workspace_dir not in requested.parents:
            raise ValueError("Path traversal outside workspace is not allowed.")
        return requested


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the configured workspace directory."
    risk_level = RiskLevel.READ_ONLY
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."}
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_dir: Path) -> None:
        self.guard = WorkspacePathGuard(workspace_dir)

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = self.guard.resolve(arguments.get("path", ""))
        if not path.is_file():
            raise ValueError(f"File does not exist: {path.name}")
        content = path.read_text(encoding="utf-8")
        return ToolResult(ok=True, content=content, data={"path": str(path)})


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Search file names and text content inside the configured workspace directory."
    risk_level = RiskLevel.READ_ONLY
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to search for."},
            "limit": {"type": "integer", "description": "Maximum results.", "default": 20},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.guard = WorkspacePathGuard(workspace_dir)

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string.")
        limit = min(int(arguments.get("limit", 20)), 50)
        results: list[dict[str, Any]] = []

        for path in self.workspace_dir.rglob("*"):
            if len(results) >= limit:
                break
            if not path.is_file():
                continue
            rel = path.relative_to(self.workspace_dir).as_posix()
            matched = query.lower() in rel.lower()
            snippet = ""
            if not matched:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                index = text.lower().find(query.lower())
                if index >= 0:
                    matched = True
                    snippet = text[max(0, index - 80) : index + len(query) + 80]
            if matched:
                results.append({"path": rel, "snippet": snippet})

        return ToolResult(ok=True, content=str(results), data=results)
