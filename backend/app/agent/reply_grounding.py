"""Post-generation grounding review for model-authored chat replies.

This is an output reviewer, not a banking agent and not the tool-call Guard.
It never executes tools, authorizes actions or changes risk levels. A rejected
reply is rewritten once by the main model; the reviewed facts always come from
authenticated Tool observations in the current turn.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Any, Protocol

from app.agent.llm import LLMProvider
from app.agent.prompt_assembly import (
    assemble_reply_grounding_prompt, assemble_reply_rewrite_prompt,
)
from app.risk.injection import detect_injection
from app.tools.presentation import render_tool_result


class ReplyGroundingError(RuntimeError):
    """The reviewer is unavailable or returned an unusable verdict."""


class ReplyGroundingRejected(RuntimeError):
    """The reply remained unsupported after one bounded rewrite."""


@dataclass(frozen=True)
class GroundingVerdict:
    grounded: bool
    issues: tuple[str, ...] = ()


_ISSUE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_MAX_VERDICT_CHARS = 800
_MAX_REWRITE_CHARS = 1200
_MAX_FACTS_CHARS = 12000
_MAX_REQUEST_CHARS = 1600


def _tool_facts(tool_results: list[tuple[str, dict[str, Any]]]) -> str:
    """Build a bounded, server-rendered fact sheet without internal tokens."""
    lines: list[str] = []
    for name, result in tool_results:
        if not isinstance(result, dict):
            continue
        if result.get("ok") is not True:
            error = result.get("error")
            lines.append(f"[{name}] failed: {str(error or '')[:200]}")
            continue
        try:
            rendered = render_tool_result(name, result)
        except (TypeError, KeyError, IndexError, ValueError):
            rendered = "ok"
        lines.append(f"[{name}] {rendered}")
    return "\n".join(lines)[:_MAX_FACTS_CHARS]


def _safe_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > limit or detect_injection(text).blocked:
        return ""
    return text


def _parse_verdict(raw: str) -> GroundingVerdict:
    if not raw or len(raw) > _MAX_VERDICT_CHARS:
        raise ReplyGroundingError("invalid verdict size")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ReplyGroundingError("invalid verdict json") from exc
    if not isinstance(decoded, dict) or set(decoded) != {"grounded", "issues"}:
        raise ReplyGroundingError("invalid verdict shape")
    grounded = decoded["grounded"]
    issues = decoded["issues"]
    if type(grounded) is not bool or not isinstance(issues, list) or len(issues) > 8:
        raise ReplyGroundingError("invalid verdict values")
    normalized: list[str] = []
    for issue in issues:
        if (not isinstance(issue, str) or not _ISSUE_CODE.fullmatch(issue)
                or issue in normalized):
            raise ReplyGroundingError("invalid issue code")
        normalized.append(issue)
    if grounded and normalized:
        raise ReplyGroundingError("grounded verdict has issues")
    if not grounded and not normalized:
        normalized = ["unsupported_claim"]
    return GroundingVerdict(grounded=grounded, issues=tuple(normalized))


class ReplyGrounding:
    def __init__(self, model: LLMProvider, *, timeout: float = 8.0) -> None:
        self.model = model
        self.timeout = timeout

    async def verify(
        self, candidate: str, *, user_request: str,
        tool_results: list[tuple[str, dict[str, Any]]],
        action_status: str = "none",
    ) -> GroundingVerdict:
        request = _safe_text(user_request, _MAX_REQUEST_CHARS)
        # The candidate is untrusted data. A blocked-looking candidate is still
        # reviewed rather than treated as an instruction.
        payload = {
            "user_request": request,
            "candidate": candidate[:1500],
            "tool_results": _tool_facts(tool_results),
            "action_status": action_status[:80],
        }
        messages = assemble_reply_grounding_prompt().model_messages()
        messages.append({"role": "user", "content": json.dumps(
            payload, ensure_ascii=False,
        )})
        chunks: list[str] = []
        try:
            async with asyncio.timeout(self.timeout):
                async for chunk in self.model.stream(messages, tools=None):
                    if getattr(chunk, "tool_calls", None):
                        raise ReplyGroundingError("reviewer attempted a tool call")
                    part = getattr(chunk, "content", "") or ""
                    if not isinstance(part, str):
                        raise ReplyGroundingError("reviewer returned non-text")
                    chunks.append(part)
                    if sum(len(item) for item in chunks) > _MAX_VERDICT_CHARS:
                        raise ReplyGroundingError("reviewer output too long")
        except ReplyGroundingError:
            raise
        except Exception as exc:
            raise ReplyGroundingError("reviewer unavailable") from exc
        return _parse_verdict("".join(chunks))

    async def rewrite(
        self, candidate: str, *, user_request: str,
        tool_results: list[tuple[str, dict[str, Any]]],
        issues: tuple[str, ...], action_status: str = "none",
    ) -> str:
        request = _safe_text(user_request, _MAX_REQUEST_CHARS)
        payload = {
            "user_request": request,
            "previous_reply": candidate[:1500],
            "issues": list(issues),
            "tool_results": _tool_facts(tool_results),
            "action_status": action_status[:80],
        }
        messages = assemble_reply_rewrite_prompt().model_messages()
        messages.append({"role": "user", "content": json.dumps(
            payload, ensure_ascii=False,
        )})
        chunks: list[str] = []
        try:
            async with asyncio.timeout(self.timeout):
                async for chunk in self.model.stream(messages, tools=None):
                    if getattr(chunk, "tool_calls", None):
                        raise ReplyGroundingError("rewrite attempted a tool call")
                    part = getattr(chunk, "content", "") or ""
                    if not isinstance(part, str):
                        raise ReplyGroundingError("rewrite returned non-text")
                    chunks.append(part)
                    if sum(len(item) for item in chunks) > _MAX_REWRITE_CHARS:
                        raise ReplyGroundingError("rewrite output too long")
        except ReplyGroundingError:
            raise
        except Exception as exc:
            raise ReplyGroundingError("rewrite unavailable") from exc
        text = "".join(chunks).strip()
        if not text or _MAX_REWRITE_CHARS < len(text):
            raise ReplyGroundingError("empty rewrite")
        return text

    async def compose(
        self, candidate: str, *, user_request: str,
        tool_results: list[tuple[str, dict[str, Any]]],
        action_status: str = "none",
    ) -> str:
        """Return a reviewed reply or raise without emitting unverified text."""
        if not candidate.strip():
            raise ReplyGroundingRejected("empty candidate")
        verdict = await self.verify(
            candidate, user_request=user_request,
            tool_results=tool_results, action_status=action_status,
        )
        if verdict.grounded:
            return candidate
        rewritten = await self.rewrite(
            candidate, user_request=user_request,
            tool_results=tool_results, issues=verdict.issues,
            action_status=action_status,
        )
        second = await self.verify(
            rewritten, user_request=user_request,
            tool_results=tool_results, action_status=action_status,
        )
        if second.grounded:
            return rewritten
        raise ReplyGroundingRejected("rewrite still ungrounded")


def get_reply_grounding(model: LLMProvider) -> ReplyGrounding:
    return ReplyGrounding(model)
