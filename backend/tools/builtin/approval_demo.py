from typing import Any

from backend.tools.base import RiskLevel, Tool, ToolResult


class ApprovalDemoTool(Tool):
    name = "approval_demo"
    description = "Demonstrate a human-approved WRITE-risk tool without touching the OS."
    risk_level = RiskLevel.WRITE
    input_schema = {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why this action needs approval."}
        },
        "required": ["reason"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        reason = arguments.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string.")
        return ToolResult(
            ok=True,
            content=f"Approved WRITE-risk demo action completed: {reason}",
            data={"reason": reason},
        )
