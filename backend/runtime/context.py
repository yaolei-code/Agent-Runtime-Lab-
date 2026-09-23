from typing import Any


class ContextBuilder:
    def build(
        self,
        messages: list[dict[str, Any]],
        memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are Personal Agent Hub v2, an agent harness runtime. "
                    "Use tools when useful. If a tool result is available, use it "
                    "to produce a concise final answer."
                ),
            }
        ]

        if memories:
            memory_lines = [
                f"- [{item['type']}] {item['content']} (source: {item['source']})"
                for item in memories
            ]
            context.append(
                {
                    "role": "system",
                    "content": "Relevant long-term memory:\n" + "\n".join(memory_lines),
                }
            )

        context.extend(messages)
        return context
