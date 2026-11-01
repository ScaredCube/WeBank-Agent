"""Durable, user-scoped deduplication of SSE-based Agent requests.

The unique (user_id, request_id) constraint is the database concurrency arbiter.
Retries never execute tools and NEVER receive an old action confirmation token.
"""
import hashlib
import hmac
import json

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.time import utcnow
from app.core.config import settings
from app.db.session import session_scope
from app.models import ChatSubmission


class SubmissionConflict(ValueError):
    pass


def fingerprint(content: str, references: list) -> str:
    refs = sorted((str(ref.kind), int(ref.id)) for ref in references)
    body = json.dumps({"content": content, "references": refs},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # Keyed digest avoids exposing guessable message contents via an ordinary
    # SHA256 dictionary check if the database is ever leaked.
    return hmac.new(settings.data_hmac_key.encode("utf-8"),
                    body.encode("utf-8"), hashlib.sha256).hexdigest()


def claim_submission(session: Session, *, user_id: int, conversation_id: int,
                     request_id: str, payload_digest: str) -> tuple[ChatSubmission, bool]:
    candidate = ChatSubmission(user_id=user_id, conversation_id=conversation_id,
                               request_id=request_id, payload_digest=payload_digest)
    try:
        with session.begin_nested():
            session.add(candidate)
            session.flush()
        session.commit()
        return candidate, True
    except IntegrityError:
        # Savepoint isolates a legitimate unique-key collision from other work.
        existing = session.exec(select(ChatSubmission).where(
            ChatSubmission.user_id == user_id,
            ChatSubmission.request_id == request_id,
        )).first()
        if existing is None:
            raise SubmissionConflict("请求状态暂不可用，请查看历史记录") from None
        if existing.conversation_id != conversation_id or existing.payload_digest != payload_digest:
            raise SubmissionConflict("该请求编号已用于另一条消息，请创建新请求") from None
        return existing, False


def advance_submission(*, submission_id: int | None, state: str,
                       user_message_id: int | None = None,
                       assistant_message_id: int | None = None,
                       pending_action_id: int | None = None) -> None:
    if submission_id is None:
        return
    with session_scope() as session:
        attempt = session.get(ChatSubmission, submission_id)
        if attempt is None:
            return
        # A terminal result must never regress to "processing" on retry.
        if attempt.state == "action_pending" and state != "action_pending":
            return
        if attempt.state == "completed" and state != "completed":
            return
        attempt.state = state
        if user_message_id is not None:
            attempt.user_message_id = user_message_id
        if assistant_message_id is not None:
            attempt.assistant_message_id = assistant_message_id
        if pending_action_id is not None:
            attempt.pending_action_id = pending_action_id
        attempt.updated_at = utcnow()
        session.add(attempt)
        session.commit()
