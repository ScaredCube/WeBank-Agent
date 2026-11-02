"""Compile conversation history and verified application notes for a model turn.

This is an in-memory projection, not a memory store or authorization layer.
The authenticated chat boundary must resolve bank ownership and mint any tokens
before calling this module. User text must never become a TrustedContextNote
merely because it resembles a server annotation.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.risk.injection import detect_injection


HistoryRole = Literal["user", "assistant"]
NoteSource = Literal[
    "validated_intent", "verified_object", "temporary_phone_reference",
    "trusted_bill_context", "readonly_selection", "trusted_view_context",
]
_BLOCKED_TEXT = "[已拦截的可疑输入]"
_ALLOWED_NOTE_SOURCES = frozenset((
    "validated_intent", "verified_object", "temporary_phone_reference",
    "trusted_bill_context", "readonly_selection", "trusted_view_context",
))


@dataclass(frozen=True)
class TrustedContextNote:
    """Already checked, model-visible application context.

    This is a presentation carrier, NOT proof of authorization. Validation
    remains in the chat/service layer and bank tools. The content is not
    included in audit metadata or object representations.
    """

    source: NoteSource
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.source not in _ALLOWED_NOTE_SOURCES:
            raise ValueError("Unknown trusted context source")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Trusted context note cannot be empty")


@dataclass(frozen=True)
class ConversationContextInput:
    """One current user turn plus previous persisted messages.

    model_request is the caller-prepared model text, possibly redacted.
    It may differ from original_request. The current user database row must
    NOT be included in prior_messages: provide preceding historical rows.
    max_history counts the current turn.
    """

    original_request: str = field(repr=False)
    model_request: str = field(repr=False)
    prior_messages: Sequence[Mapping[str, str]] = field(repr=False)
    notes: tuple[TrustedContextNote, ...] = ()
    validated_intent_prefix: str | None = field(default=None, repr=False)
    max_history: int = 20
    current_input_blocked: bool = False


@dataclass(frozen=True)
class PreparedContext:
    """Immutable conversation snapshot; callers receive fresh model mappings."""

    original_request: str = field(repr=False)
    _message_pairs: tuple[tuple[HistoryRole, str], ...] = field(repr=False)
    sources: tuple[str, ...]
    historical_messages: int
    masked_history_messages: int

    def model_messages(self) -> list[dict[str, str]]:
        return [{"role": role, "content": content} for role, content in self._message_pairs]


def assemble_context(source: ConversationContextInput) -> PreparedContext:
    """Produce one current user message following bounded prior history.

    Historical content stays in its user/assistant role. Suspicious old messages
    are masked instead of elevated to system instructions. Validated notes stay
    as current-turn context, never higher-priority model messages.

    Reply policies should use original_request, not reverse-parse model text.
    """
    if source.max_history < 1:
        raise ValueError("max_history must reserve at least one current message")
    if not isinstance(source.original_request, str) or not isinstance(source.model_request, str):
        raise TypeError("current request and model request must be strings")
    if not source.original_request.strip():
        raise ValueError("current user request cannot be empty")

    prior = source.prior_messages[-(source.max_history - 1):] if source.max_history > 1 else ()
    pairs: list[tuple[HistoryRole, str]] = []
    masked = 0
    for message in prior:
        role = message.get("role")
        content = message.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise ValueError("history accepts only user/assistant text messages")
        if detect_injection(content).blocked:
            content = _BLOCKED_TEXT
            masked += 1
        pairs.append((role, content))

    if source.current_input_blocked:
        current = _BLOCKED_TEXT
        current_sources: list[str] = ["blocked_current_user"]
    else:
        # Match existing intent-prompt semantics: a validated drag intent
        # precedes the free-form user message without granting authorization.
        parts = []
        current_sources = []
        if source.validated_intent_prefix:
            parts.append(source.validated_intent_prefix)
            current_sources.append("validated_intent")
        parts.append(source.model_request)
        current_sources.append("current_user")
        for note in source.notes:
            parts.append(note.content)
            current_sources.append(note.source)
        current = "\n\n".join(parts)

    pairs.append(("user", current))
    return PreparedContext(
        original_request=source.original_request,
        _message_pairs=tuple(pairs),
        sources=tuple(["recent_history"] * len(prior) + current_sources),
        historical_messages=len(prior),
        masked_history_messages=masked,
    )
