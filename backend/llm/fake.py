import re
from typing import Any

from backend.llm.base import LLMProvider
from backend.runtime.actions import AgentAction, FinalAnswerAction, ToolCallAction


class FakeRuleBasedProvider(LLMProvider):
    """Local demo provider for UI and integration demos without a real API key."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentAction:
        if messages and messages[-1]["role"] == "tool":
            return FinalAnswerAction(
                kind="final_answer",
                content=f"Tool result: {messages[-1].get('content')}",
            )

        user_message = next(
            (item.get("content", "") for item in reversed(messages) if item["role"] == "user"),
            "",
        )
        if "approval" in user_message.lower() or "审批" in user_message:
            return ToolCallAction(
                kind="tool_call",
                call_id="fake_call_approval",
                tool_name="approval_demo",
                arguments={"reason": user_message},
                assistant_message=self._assistant_message(
                    "fake_call_approval",
                    "approval_demo",
                    '{"reason": "demo approval"}',
                ),
            )

        expression = self._extract_expression(user_message)
        if expression:
            return ToolCallAction(
                kind="tool_call",
                call_id="fake_call_calculator",
                tool_name="calculator",
                arguments={"expression": expression},
                assistant_message=self._assistant_message(
                    "fake_call_calculator",
                    "calculator",
                    f'{{"expression": "{expression}"}}',
                ),
            )

        return FinalAnswerAction(
            kind="final_answer",
            content="Fake provider received the message. Configure LLM_PROVIDER=openai for a real model.",
        )

    def _extract_expression(self, text: str) -> str | None:
        match = re.search(r"[-+*/().\d\s]{3,}", text)
        if not match:
            return None
        expression = match.group(0).strip()
        return expression if any(op in expression for op in "+-*/") else None

    def _assistant_message(self, call_id: str, name: str, arguments: str) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
