"""OpenAI-compatible Chat Completions provider adapter。

这是唯一理解 OpenAI SDK response object 的层。它把原生 tool-calling
响应转换成 runtime 的 FinalAnswerAction 或 ToolCallAction，从而让
Agent Loop 保持 provider-neutral。
"""

import json
from typing import Any

from openai import OpenAI

from backend.config.settings import Settings
from backend.llm.base import LLMProvider, LLMProviderError
from backend.runtime.actions import AgentAction, FinalAnswerAction, ToolCallAction


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible Chat Completions API 的适配器。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key:
            raise LLMProviderError("LLM_API_KEY is required.")
        if not settings.llm_model:
            raise LLMProviderError("LLM_MODEL is required.")

        self.model = settings.llm_model
        self.client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentAction:
        """调用模型，并把响应归一化成 runtime action。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if tool_calls:
            # 当前版本每轮 loop 只处理一个 tool call。未来如果要支持多个，
            # 可以引入 multi-tool action 或队列。
            tool_call = tool_calls[0]
            arguments = self._parse_arguments(tool_call.function.arguments)
            return ToolCallAction(
                kind="tool_call",
                call_id=tool_call.id,
                tool_name=tool_call.function.name,
                arguments=arguments,
                assistant_message=self._assistant_message_to_dict(message),
            )

        return FinalAnswerAction(kind="final_answer", content=message.content or "")

    def _parse_arguments(self, raw_arguments: str | None) -> dict[str, Any]:
        """把 provider 输出的 JSON 参数解析成工具执行所需的 dict。"""

        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Tool arguments are not valid JSON: {raw_arguments}") from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError("Tool arguments must be a JSON object.")
        return parsed

    def _assistant_message_to_dict(self, message: Any) -> dict[str, Any]:
        """保留 assistant tool-call message，供下一轮 provider 调用使用。"""

        payload: dict[str, Any] = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": item.id,
                    "type": "function",
                    "function": {
                        "name": item.function.name,
                        "arguments": item.function.arguments,
                    },
                }
                for item in message.tool_calls
            ]
        return payload
