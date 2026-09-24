"""LLM provider 返回给 runtime 的内部动作。

Provider adapter 会把供应商特定响应转换成这些小型 runtime action。
AgentRuntime 只根据这些类型做分发，因此 harness 不会绑定在某一个
OpenAI-compatible 或未来 provider 的响应对象上。
"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class FinalAnswerAction:
    """模型认为 run 可以用这个答案结束。"""

    kind: Literal["final_answer"]
    content: str


@dataclass(frozen=True)
class ToolCallAction:
    """模型请求调用一个已注册工具。"""

    kind: Literal["tool_call"]
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    # 需要持久化，approval resume 时靠它重建 provider 对话上下文。
    assistant_message: dict[str, Any]


AgentAction = FinalAnswerAction | ToolCallAction
