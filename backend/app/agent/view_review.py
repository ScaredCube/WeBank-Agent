"""Post-generation review for AI-composed read-only views.

This reviewer is independent of the tool-call Guard. It never executes tools,
changes risk levels or authorizes banking actions. A rejected view is
regenerated; a view that cannot pass is simply not rendered.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Any, Protocol

from app.agent.llm import LLMProvider
from app.agent.prompt_assembly import assemble_view_review_prompt
from app.risk.injection import detect_injection


class ViewReviewError(RuntimeError):
    """The reviewer is unavailable or returned an unusable verdict."""


@dataclass(frozen=True)
class ViewReviewVerdict:
    valid: bool
    issues: tuple[str, ...] = ()


_ISSUE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_MAX_VERDICT_CHARS = 800
_MAX_PAYLOAD_CHARS = 48000


def _safe_text(value: object, limit: int = 1600) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > limit or detect_injection(text).blocked:
        return ""
    return text


def _parse_verdict(raw: str) -> ViewReviewVerdict:
    if not raw or len(raw) > _MAX_VERDICT_CHARS:
        raise ViewReviewError("invalid verdict size")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ViewReviewError("invalid verdict json") from exc
    if not isinstance(decoded, dict) or set(decoded) != {"valid", "issues"}:
        raise ViewReviewError("invalid verdict shape")
    valid = decoded["valid"]
    issues = decoded["issues"]
    if type(valid) is not bool or not isinstance(issues, list) or len(issues) > 8:
        raise ViewReviewError("invalid verdict values")
    normalized: list[str] = []
    for issue in issues:
        if (not isinstance(issue, str) or not _ISSUE_CODE.fullmatch(issue)
                or issue in normalized):
            raise ViewReviewError("invalid issue code")
        normalized.append(issue)
    if valid and normalized:
        raise ViewReviewError("valid verdict has issues")
    if not valid and not normalized:
        normalized = ["other"]
    return ViewReviewVerdict(valid=valid, issues=tuple(normalized))


class ViewReviewer:
    def __init__(self, model: LLMProvider, *, timeout: float = 8.0) -> None:
        self.model = model
        self.timeout = timeout

    async def review(
        self, *, user_request: str, source_data: dict[str, Any],
        view_data: dict[str, Any], spec: dict[str, Any],
    ) -> ViewReviewVerdict:
        payload = json.dumps({
            "user_request": _safe_text(user_request),
            "source_data": source_data,
            "view_data": view_data,
            "spec": spec,
        }, ensure_ascii=False)
        if len(payload) > _MAX_PAYLOAD_CHARS:
            raise ViewReviewError("review payload too large")
        messages = assemble_view_review_prompt().model_messages()
        messages.append({"role": "user", "content": payload})
        chunks: list[str] = []
        try:
            async with asyncio.timeout(self.timeout):
                async for chunk in self.model.stream(messages, tools=None):
                    if getattr(chunk, "tool_calls", None):
                        raise ViewReviewError("reviewer attempted a tool call")
                    part = getattr(chunk, "content", "") or ""
                    if not isinstance(part, str):
                        raise ViewReviewError("reviewer returned non-text")
                    chunks.append(part)
                    if sum(len(item) for item in chunks) > _MAX_VERDICT_CHARS:
                        raise ViewReviewError("reviewer output too long")
        except ViewReviewError:
            raise
        except Exception as exc:
            raise ViewReviewError("reviewer unavailable") from exc
        return _parse_verdict("".join(chunks))


def get_view_reviewer(model: LLMProvider) -> ViewReviewer:
    return ViewReviewer(model)
