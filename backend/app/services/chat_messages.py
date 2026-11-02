"""Presentation and atomic persistence of authenticated chat results."""

from sqlmodel import Session, select

from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Conversation, Message, MessageResult, MessageView, ChatSubmission
from app.schemas.chat import MessageOut
from app.schemas.generative_ui import ViewEnvelope
from app.schemas.tool_results import ToolResultBundle, ToolResultItem
from app.services.chat_submissions import advance_submission
from app.services.vault import VaultError, encrypt_result_snapshot, decrypt_result_snapshot


_UNSET_SNAPSHOT = object()


def present_message(
    session: Session, message: Message,
    snapshot: MessageResult | None | object = _UNSET_SNAPSHOT,
    view_snapshots: dict[int, object] | None = None,
) -> MessageOut:
    output = MessageOut.model_validate(message)
    if message.role != "assistant":
        return output
    if view_snapshots is None:
        from app.services.view_service import load_views_for_messages
        view_snapshots = load_views_for_messages(session, [message])
    view = view_snapshots.get(message.id)
    if view is not None:
        output = output.model_copy(update={"ui_view": view.model_dump(mode="json")})
    if snapshot is _UNSET_SNAPSHOT:
        snapshot = session.exec(select(MessageResult).where(MessageResult.message_id == message.id)).first()
    if not isinstance(snapshot, MessageResult) or snapshot.kind not in ("monthly_bill", "card_status", "internal_transfer", "tool_results"):
        return output
    try:
        payload = decrypt_result_snapshot(snapshot.ciphertext, snapshot.key_version)
        if snapshot.kind == "tool_results":
            validated = ToolResultBundle.model_validate(payload)
        else:
            validated = ToolResultBundle(items=[ToolResultItem(
                kind=snapshot.kind, data=payload
            )])
        values = [item.model_dump() for item in validated.items]
        first_bill = next((item["data"] for item in values if item["kind"] == "monthly_bill"), None)
        first_card = next((item["data"] for item in values if item["kind"] == "card_status"), None)
        return output.model_copy(update={
            "tool_results": values, "bill_result": first_bill, "card_result": first_card,
        })
    except (VaultError, ValueError):
        # History remains readable when old/retired encryption keys are unavailable.
        return output


def persist_assistant(conversation_id: int, content: str,
                       bill_result: dict | None = None, card_result: dict | None = None,
                       tool_results: list[dict] | None = None,
                      submission_id: int | None = None, *, finalize: bool = True,
                      view: ViewEnvelope | None = None) -> dict | None:
    if not content and not (tool_results or bill_result or card_result):
        if submission_id is not None:
            advance_submission(submission_id=submission_id, state="completed")
        return None
    if not content:
        content = "已完成查询，结果见下方卡片。"
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        message = Message(conversation_id=conversation_id, role="assistant", content=content)
        session.add(message)
        conversation.updated_at = utcnow()
        session.flush()
        data = tool_results if tool_results is not None else (
            ([{"kind": "monthly_bill", "data": bill_result}] if bill_result is not None else [])
            + ([{"kind": "card_status", "data": card_result}] if card_result is not None else [])
        )
        if data:
            validated = ToolResultBundle.model_validate({"items": data})
            if len(validated.items) == 1:
                item = validated.items[0]
                snapshot_kind, payload = item.kind, item.data
            else:
                snapshot_kind, payload = "tool_results", validated.model_dump()
            ciphertext, key_version = encrypt_result_snapshot(payload)
            session.add(MessageResult(
                message_id=message.id, kind=snapshot_kind,
                ciphertext=ciphertext, key_version=key_version))
        if view is not None:
            if view.conversation_id != conversation_id:
                raise RuntimeError("View ownership invariant failed")
            session.add(MessageView(message_id=message.id, view_id=view.view_id,
                                    revision=view.revision))
        if submission_id is not None:
            # Atomic success boundary: persisted response and request completion
            # must commit together, never in two separate transactions.
            submission = session.get(ChatSubmission, submission_id)
            if submission is None or submission.conversation_id != conversation_id:
                raise RuntimeError("Chat submission ownership invariant failed")
            # A prepared action remains pending even though its assistant
            # placeholder message is now durable; do not overwrite the replay
            # state with "completed".
            if finalize and submission.state != "action_pending":
                submission.state = "completed"
            submission.assistant_message_id = message.id
            submission.updated_at = utcnow()
            session.add(submission)
        session.commit()
        return present_message(session, message).model_dump(mode="json")


def finalize_assistant(conversation_id: int, message_id: int, *,
                       submission_id: int | None = None, view=None) -> dict:
    """Complete a saved reply after optional view generation."""
    with session_scope() as session:
        message = session.get(Message, message_id)
        if message is None or message.conversation_id != conversation_id or message.role != "assistant":
            raise RuntimeError("Assistant message ownership invariant failed")
        if view is not None:
            from app.models import MessageView
            if view.conversation_id != conversation_id:
                raise RuntimeError("View ownership invariant failed")
            session.add(MessageView(message_id=message_id, view_id=view.view_id, revision=view.revision))
        if submission_id is not None:
            submission = session.get(ChatSubmission, submission_id)
            if (submission is None or submission.conversation_id != conversation_id
                    or submission.assistant_message_id != message_id):
                raise RuntimeError("Chat submission ownership invariant failed")
            if submission.state != "action_pending":
                submission.state = "completed"
            submission.updated_at = utcnow()
            session.add(submission)
        session.commit()
        return present_message(session, message).model_dump(mode="json")


def present_messages(session: Session, messages: list[Message]) -> list[MessageOut]:
    # One batch instead of a SELECT per assistant message; preserve each
    # message's historical encrypted result and the existing failure fallback.
    assistant_ids = [message.id for message in messages if message.role == "assistant" and message.id is not None]
    snapshots: dict[int, MessageResult] = {}
    # Legacy clients may still request the entire transcript. Chunk the IN
    # clause so even a very long conversation stays below SQLite bind limits.
    for offset in range(0, len(assistant_ids), 400):
        chunk = assistant_ids[offset:offset + 400]
        snapshots.update({
            row.message_id: row for row in session.exec(
                select(MessageResult).where(MessageResult.message_id.in_(chunk))
            ).all()
        })
    from app.services.view_service import load_views_for_messages
    views = load_views_for_messages(session, messages)
    return [present_message(session, message, snapshot=snapshots.get(message.id),
                            view_snapshots=views)
            for message in messages]
