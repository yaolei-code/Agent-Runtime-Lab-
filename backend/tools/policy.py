"""Agent Harness 的工具策略决策。

LLM 可以请求工具，但 harness 决定工具是否允许运行。
这个模块是执行模型所选代码前的第一道安全边界。
"""

from dataclasses import dataclass
from enum import StrEnum

from backend.tools.base import RiskLevel, Tool


class PolicyDecisionType(StrEnum):
    """一次工具调用请求可能得到的策略结果。"""

    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    BLOCK = "block"


@dataclass(frozen=True)
class PolicyDecision:
    """策略结果，以及会写入 trace/approval 的人类可读原因。"""

    decision: PolicyDecisionType
    reason: str


class ToolPolicy:
    """基于风险等级的策略引擎。

    默认策略允许只读工具；对写入、执行、外部副作用类工具要求人工审批。
    BLOCK 也被支持，方便更严格的部署或测试场景。
    """

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
        """在执行前对一次工具请求做策略分类。"""

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
