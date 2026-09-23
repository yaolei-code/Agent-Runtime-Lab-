from abc import ABC, abstractmethod
from typing import Any

from backend.runtime.actions import AgentAction


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentAction:
        raise NotImplementedError
