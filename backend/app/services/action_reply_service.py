"""Generate the chat reply after a fixed action dialog reaches a terminal state."""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.agent.action_reply import compose_action_reply
from app.agent.llm import LLMProvider, get_llm
from app.core.time import utcnow
from app.models import ChatSubmission, Conversation, Message, PendingAction
from app.services.chat_messages import present_message
from app.services.redaction import mask_text

TERMINAL_STATUSES = frozenset({"completed", "cancelled", "expired"})
_SAFE_DETAIL_KEYS = {
    "amount_fen", "recipient_name", "recipient_phone_masked", "note",
    "card_id", "masked_number", "account_name", "order_type",
    "product_name", "subscription_name", "source_name", "target_name",
    "status",
}


def _safe_details(raw: str) -> dict[str, Any]:
    try:
        details = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(details, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if key not in _SAFE_DETAIL_KEYS:
            continue
        if isinstance(value, str):
            safe[key] = mask_text(value)[:160]
        elif type(value) in (int, bool):
            safe[key] = value
    return safe


def action_facts(action: PendingAction) -> dict[str, Any]:
    return {
        "action_type": action.action_type,
        "status": action.status,
        "risk_level": action.risk_level,
        "details": _safe_details(action.details_json),
    }


async def compose_and_persist_action_reply(
    session: Session, *, user_id: int, action_id: int,
    model: LLMProvider | None = None,
) -> dict[str, Any] | None:
    action = session.get(PendingAction, action_id)
    if action is None or action.user_id != user_id:
        return None
    if action.status not in TERMINAL_STATUSES:
        return None
    submission = session.exec(select(ChatSubmission).where(
        ChatSubmission.user_id == user_id,
        ChatSubmission.pending_action_id == action.id,
    ).order_by(ChatSubmission.id.desc())).first()
    if submission is None:
        return None

    existing = (session.get(Message, submission.assistant_message_id)
                if submission.assistant_message_id is not None else None)
    if (existing is not None and existing.content.strip()
            and submission.state == "completed"):
        return present_message(session, existing).model_dump(mode="json")

    text = await compose_action_reply(
        action_facts(action), model=model or get_llm(),
    )
    conversation = session.get(Conversation, submission.conversation_id)
    if conversation is None:
        return None
    now = utcnow()
    if text is None:
        # The action is terminal; keep the card/visible result usable even when
        # the optional reply wording cannot be generated. No fixed fallback.
        submission.state = "completed"
        submission.updated_at = now
        session.add(submission)
        session.commit()
        return None

    if existing is not None:
        existing.content = text
        message = existing
    else:
        message = Message(
            conversation_id=submission.conversation_id,
            role="assistant", content=text,
        )
        session.add(message)
        session.flush()
    submission.assistant_message_id = message.id
    submission.state = "completed"
    submission.updated_at = now
    conversation.updated_at = now
    session.add(submission)
    session.add(conversation)
    session.commit()
    session.refresh(message)
    return present_message(session, message).model_dump(mode="json")
