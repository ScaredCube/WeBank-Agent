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


class LLMConfigurationError(RuntimeError):
    """Raised when the application is started without a usable LLM key."""


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


def validate_llm_config() -> None:
    """Fail fast: the application has no deterministic reply fallback."""
    if not settings.llm_api_key.strip():
        raise LLMConfigurationError(
            "LLM_API_KEY 未配置；本版本不提供离线 Mock 或固定回复兜底，"
            "请配置可用的 OpenAI 兼容模型后再启动。"
        )


@lru_cache
def get_llm() -> LLMProvider:
    validate_llm_config()
    return OpenAIProvider()


def get_llm_info() -> dict[str, str]:
    return {
        "mode": "openai" if settings.llm_api_key.strip() else "unconfigured",
        "model": settings.llm_model,
    }
