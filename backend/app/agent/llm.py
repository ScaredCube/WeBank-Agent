import asyncio
from secrets import token_bytes
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from openai import AsyncOpenAI

from app.core.config import settings


def _new_internal_tool_call_id() -> str:
    """Opaque model call IDs are transport metadata, not trusted bank reference data.

    Generate a random letter-only correlation ID so third-party numeric IDs cannot
    collide with the account/phone redaction rules. The same generated ID is used
    in assistant tool_calls and the matching tool response.
    """
    alphabet = "abcdefghijklmnop"
    return "call_" + "".join(alphabet[byte >> 4] + alphabet[byte & 15] for byte in token_bytes(16))


@dataclass
class LLMChunk:
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class LLMProvider(Protocol):
    mode: str
    model: str

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]: ...


class MockProvider:
    mode = "mock"

    def __init__(self, model: str) -> None:
        self.model = model

    def _compose(self, messages: list[dict[str, Any]]) -> str:
        last_user = next(
            (message["content"] for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        snippet = last_user.strip().replace("\n", " ")[:24]
        if not snippet:
            return "你好，我是小We。当前是演示模式，可以陪你了解银行功能和使用流程。"
        return (
            f"收到你说的「{snippet}」。当前是演示模式，离线 Mock 不会调用银行工具，"
            "只能用于测试对话链路。转账、账单分析和卡片管理尚未开放。"
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        text = self._compose(messages)
        for index in range(0, len(text), 3):
            await asyncio.sleep(0.012)
            yield LLMChunk(content=text[index : index + 3])
        yield LLMChunk(finish_reason="stop")


class OpenAIProvider:
    mode = "openai"

    def __init__(self) -> None:
        self.model = settings.llm_model
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            default_headers=settings.llm_extra_headers or None,
            timeout=settings.llm_timeout,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            request["tools"] = tools

        stream = await self._client.chat.completions.create(**request)
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield LLMChunk(content=delta.content)

            if delta.tool_calls:
                for call in delta.tool_calls:
                    slot = tool_calls.setdefault(
                        call.index,
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if call.id:
                        slot["id"] = call.id
                    if call.function:
                        if call.function.name:
                            slot["function"]["name"] += call.function.name
                        if call.function.arguments:
                            slot["function"]["arguments"] += call.function.arguments

            if choice.finish_reason:
                if tool_calls:
                    for buffered in tool_calls.values():
                        if buffered["id"]:
                            buffered["id"] = _new_internal_tool_call_id()
                yield LLMChunk(
                    finish_reason=choice.finish_reason,
                    tool_calls=list(tool_calls.values()) if tool_calls else None,
                )


@lru_cache
def get_llm() -> LLMProvider:
    if not settings.llm_api_key.strip():
        return MockProvider(model="mock")
    return OpenAIProvider()


def get_llm_info() -> dict[str, str]:
    provider = get_llm()
    return {"mode": provider.mode, "model": provider.model}
