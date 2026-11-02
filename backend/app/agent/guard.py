import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.agent.llm import LLMProvider, get_llm
from app.agent.prompt_assembly import assemble_guard_prompt
from app.agent.registry import ToolSpec
from app.core.config import settings

_CHINA = timezone(timedelta(hours=8))
_MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")


@dataclass(frozen=True)
class GuardCall:
    tool: str
    purpose: str
    risk_level: str
    arguments: dict[str, Any]
    previous_tools: tuple[str, ...]
    local_time: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "purpose": self.purpose,
            "risk_level": self.risk_level,
            "arguments": self.arguments,
            "previous_tools": list(self.previous_tools),
            "local_time": self.local_time,
        }


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    reason: str


class GuardProvider(Protocol):
    async def review(self, call: GuardCall) -> GuardVerdict: ...


def build_guard_call(
    spec: ToolSpec,
    arguments: dict[str, Any],
    previous_tools: list[str] | tuple[str, ...],
    now: datetime | None = None,
) -> GuardCall:
    properties = spec.parameters.get("properties", {})
    known = set(properties) if isinstance(properties, dict) else set()
    summary: dict[str, Any] = {}
    for key in sorted(known):
        if key not in arguments:
            continue
        value = arguments[key]
        if key in {"amount_fen", "limit"} and type(value) is int:
            summary[key] = value
        elif key == "month":
            if isinstance(value, str) and _MONTH.fullmatch(value):
                summary["month"] = value
            else:
                summary["month_invalid"] = True
        elif key in {"account_token", "source_token", "target_token"}:
            summary[f"{key}_present"] = isinstance(value, str) and bool(value)
        else:
            summary[f"{key}_present"] = value is not None
    summary["unknown_argument_count"] = len(set(arguments) - known)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = datetime.now(timezone.utc)
    return GuardCall(
        tool=spec.name,
        purpose=spec.description,
        risk_level=spec.risk.value,
        arguments=summary,
        previous_tools=tuple(previous_tools),
        local_time=current.astimezone(_CHINA).isoformat(),
    )


def _parse_verdict(text: str) -> GuardVerdict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return GuardVerdict(False, "invalid_response")
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return GuardVerdict(False, "invalid_response")
    if not isinstance(payload, dict) or type(payload.get("allow")) is not bool:
        return GuardVerdict(False, "invalid_response")
    return GuardVerdict(payload["allow"], "allowed" if payload["allow"] else "rejected")


class LLMGuard:
    def __init__(self, provider: LLMProvider | None = None, timeout: float | None = None) -> None:
        self._provider = provider or get_llm()
        self._timeout = timeout if timeout is not None else settings.guard_timeout_seconds

    async def review(self, call: GuardCall) -> GuardVerdict:
        messages = assemble_guard_prompt().model_messages()
        messages.append({
            "role": "user",
            "content": json.dumps(call.to_payload(), ensure_ascii=False, sort_keys=True),
        })

        async def collect() -> str:
            parts: list[str] = []
            async for chunk in self._provider.stream(messages, tools=None):
                if chunk.content:
                    parts.append(chunk.content)
            return "".join(parts)

        try:
            text = await asyncio.wait_for(collect(), timeout=self._timeout)
        except Exception:
            return GuardVerdict(False, "unavailable")
        return _parse_verdict(text)


def get_guard() -> GuardProvider:
    return LLMGuard(get_llm())
