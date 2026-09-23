from dataclasses import dataclass
from enum import StrEnum

from backend.tools.base import RiskLevel, Tool


class PolicyDecisionType(StrEnum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    BLOCK = "block"


@dataclass(frozen=True)
class PolicyDecision:
    decision: PolicyDecisionType
    reason: str


class ToolPolicy:
    def __init__(
        self,
        approvals_required: set[RiskLevel] | None = None,
        blocked: set[RiskLevel] | None = None,
    ) -> None:
        self.approvals_required = approvals_required or {
            RiskLevel.WRITE,
            RiskLevel.EXECUTE,
            RiskLevel.EXTERNAL_SIDE_EFFECT,
        }
        self.blocked = blocked or set()

    def evaluate(self, tool: Tool) -> PolicyDecision:
        if tool.risk_level in self.blocked:
            return PolicyDecision(
                decision=PolicyDecisionType.BLOCK,
                reason=f"Tool risk level is blocked: {tool.risk_level.value}",
            )
        if tool.risk_level in self.approvals_required:
            return PolicyDecision(
                decision=PolicyDecisionType.APPROVAL_REQUIRED,
                reason=f"Tool risk level requires approval: {tool.risk_level.value}",
            )
        return PolicyDecision(decision=PolicyDecisionType.ALLOW, reason="Allowed by policy.")
