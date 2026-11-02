"""Short-lived carry-forward of a validated drag intent across one clarification.

Only entity IDs are stored. Every reuse re-checks ownership, status and amount
through the normal intent service; execution still requires the fixed dialog.
"""
from __future__ import annotations

import re

from sqlmodel import Session, select

from app.core.time import utcnow
from app.models import ConversationIntent
from app.schemas.chat import ChatIntent

_AFFIRM = re.compile(
    r"^\s*(?:是|是的|对|对的|好|好的|可以|行|嗯|确认|没问题|继续|按这个|就这个)"
    r"\s*[。！!]?\s*$"
)
_AFFIRM_WITH_AMOUNT = re.compile(
    r"^\s*(?:是|是的|对|对的|好|好的|可以|行|嗯|确认|没问题|继续|按这个|就这个)"
    r"\s*[，,、]?\s*(?:转账金额\s*[:：]?\s*)?"
    r"[0-9]+(?:\.[0-9]{1,2})?\s*(?:元|块|分|角)\s*[。！!]?\s*$"
)


def is_short_affirmation(text: str) -> bool:
    candidate = text or ""
    return bool(_AFFIRM.fullmatch(candidate) or _AFFIRM_WITH_AMOUNT.fullmatch(candidate))


def remember_intent(
    session: Session, *, conversation_id: int, user_id: int,
    intent: ChatIntent, amount_fen: int | None,
) -> None:
    row = session.get(ConversationIntent, conversation_id)
    if row is None:
        row = ConversationIntent(
            conversation_id=conversation_id, user_id=user_id,
            action=intent.action,
            source_kind=intent.source.kind, source_id=intent.source.id,
            target_kind=intent.target.kind, target_id=intent.target.id,
            amount_fen=amount_fen,
        )
    else:
        row.action = intent.action
        row.source_kind = intent.source.kind
        row.source_id = intent.source.id
        row.target_kind = intent.target.kind
        row.target_id = intent.target.id
        row.amount_fen = amount_fen
        row.updated_at = utcnow()
    session.add(row)
    session.flush()


def load_intent(
    session: Session, *, conversation_id: int, user_id: int,
) -> tuple[ChatIntent, int | None] | None:
    row = session.get(ConversationIntent, conversation_id)
    if row is None or row.user_id != user_id:
        return None
    try:
        intent = ChatIntent.model_validate({
            "action": row.action,
            "source": {"kind": row.source_kind, "id": row.source_id},
            "target": {"kind": row.target_kind, "id": row.target_id},
        })
    except ValueError:
        return None
    return intent, row.amount_fen


def clear_intent(session: Session, *, conversation_id: int, user_id: int) -> None:
    row = session.get(ConversationIntent, conversation_id)
    if row is not None and row.user_id == user_id:
        session.delete(row)
        session.flush()
