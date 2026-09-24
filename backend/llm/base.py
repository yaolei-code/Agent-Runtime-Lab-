"""Agent Runtime 使用的 LLM provider 边界。"""

from abc import ABC, abstractmethod
from typing import Any

from backend.runtime.actions import AgentAction


class LLMProviderError(RuntimeError):
    """当前配置的 provider 无法产出 runtime action 时抛出。"""

    pass


class LLMProvider(ABC):
    """AgentRuntime 消费的抽象模型接口。

    实现类应该隐藏 SDK/供应商细节，只返回内部 action。
    这样 runtime 的分发逻辑就不会依赖某一个模型 API。
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentAction:
        raise NotImplementedError
