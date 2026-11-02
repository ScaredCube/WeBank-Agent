"""Read-only, authenticated projection of a prepared Agent action.

A ChatSubmission remembers the original request and pending-action ID. The
PendingAction/financial services own the actual action status. This projection
never updates either record, replays a Tool or releases confirmation material.
"""
from datetime import timezone

from sqlmodel import Session, select

from app.core.time import utcnow
from app.models import ChatSubmission, PendingAction


# A verified confirmation is NOT a verified financial execution.
_STAGE = {
    "pending": ("awaiting_confirmation", "not_executed"),
    "confirmed": ("awaiting_execution", "not_executed"),
    "verified": ("awaiting_execution", "not_executed"),
    "completed": ("completed", "completed"),
    "cancelled": ("cancelled", "not_executed"),
    "expired": ("expired", "not_executed"),
}


def action_progress_for_submission(
    session: Session, *, submission: ChatSubmission,
    user_id: int, conversation_id: int,
) -> dict | None:
    """Project only the action linked to this user's own conversation request."""
    if (submission.user_id != user_id or submission.conversation_id != conversation_id
            or submission.state != "action_pending" or submission.pending_action_id is None):
        return None
    action = session.exec(select(PendingAction).where(
        PendingAction.id == submission.pending_action_id,
        PendingAction.user_id == user_id,
    )).first()
    if action is None:
        # The link exists but cannot be verified: never claim completion.
        return {
            "action_id": submission.pending_action_id,
            "status": "unknown",
            "stage": "unknown",
            "execution_state": "unknown",
        }
    action_status = action.status
    expiry = action.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    # Confirmation/verification may be recorded while the execution window
    # subsequently expires. Do not present such an action as executable.
    if action_status in {"pending", "confirmed", "verified"} and expiry <= utcnow():
        action_status = "expired"
    stage, execution = _STAGE.get(action_status, ("unknown", "unknown"))
    return {
        "action_id": action.id,
        "status": action_status,
        "stage": stage,
        "execution_state": execution,
    }


def latest_action_progress(
    session: Session, *, user_id: int, conversation_id: int,
) -> dict | None:
    """Newest prepared action in this conversation; never a payment mandate."""
    submission = session.exec(select(ChatSubmission).where(
        ChatSubmission.user_id == user_id,
        ChatSubmission.conversation_id == conversation_id,
        ChatSubmission.state == "action_pending",
        ChatSubmission.pending_action_id.is_not(None),
    ).order_by(ChatSubmission.id.desc()).limit(1)).first()
    if submission is None:
        return None
    progress = action_progress_for_submission(
        session, submission=submission, user_id=user_id,
        conversation_id=conversation_id,
    )
    if progress is None:
        return None
    return {"request_id": submission.request_id, **progress}


def replay_status_message(progress: dict | None) -> str:
    """No confirmation token or action execution on idempotent request retries."""
    stage = progress.get("stage") if progress else "unknown"
    if stage == "completed":
        return "此请求关联的操作已记录完成。请查看操作记录核对结果；不会重新执行。"
    if stage == "awaiting_execution":
        return "此请求的确认或验证已记录，但操作尚未执行。请在操作记录中核对下一步。"
    if stage == "cancelled":
        return "此请求关联的待确认操作已取消，不会重新执行。"
    if stage == "expired":
        return "此请求关联的待确认操作已过期，不能使用原确认令牌继续。"
    return "此请求已创建待确认操作，确认令牌不会重新发送。请查看操作记录；不要重复创建。"
