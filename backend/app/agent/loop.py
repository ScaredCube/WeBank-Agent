from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.registry import registry


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentLoop:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm()

    async def stream(self, history: list[dict[str, str]]) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)

        tool_calls: list[dict[str, Any]] | None = None
        try:
            async for chunk in self.llm.stream(messages, tools=registry.definitions() or None):
                if chunk.content:
                    yield AgentEvent("delta", {"text": chunk.content})
                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return

        if tool_calls:
            yield AgentEvent("action_required", {"tool_calls": tool_calls})
