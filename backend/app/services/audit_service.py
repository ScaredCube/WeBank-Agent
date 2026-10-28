"""Structured, allowlisted audit records; never accept free-text payloads."""
from contextvars import ContextVar
from uuid import uuid4

from sqlmodel import Session, select

from app.db.session import get_engine
from app.models import AuditLog, TransferRequest

request_context: ContextVar[str | None] = ContextVar("audit_request", default=None)
conversation_context: ContextVar[int | None] = ContextVar("audit_conversation", default=None)

EVENTS = frozenset({
    "tool_called", "tool_result", "risk_assessed", "transfer_prepared", "transfer_prepare_retried",
    "transfer_prepare_denied", "transfer_prepare_failed", "action_confirmed", "action_confirm_denied",
    "action_cancelled", "action_cancel_denied", "verification_started", "verification_start_denied",
    "verification_succeeded", "verification_failed", "verification_locked", "verification_denied",
    "verification_start_failed", "verification_error",
    "transfer_completed", "transfer_retried", "transfer_denied", "transfer_failed",
    # Reserved for T-207; no current code emits them.
    "token_resolved", "token_resolve_denied", "token_revoked",
})
TOOLS = frozenset({"get_account_balance", "list_recent_transactions", "get_monthly_bill", "prepare_transfer", "transfer"})
RESULTS = frozenset({"success", "denied", "failed", "retry", "locked"})
REASONS = {"工具基础风险等级": "base", "转账日累计超过限额": "daily_limit",
           "转账需要确认": "confirmation_required", "夜间操作升级": "night_upgrade"}
FAILURE_REASONS = {"insufficient_balance", "risk_upgrade", "not_authorized", "unavailable",
                   "duplicate_mismatch", "verification_unavailable", "invalid_risk", "internal_error",
                   "reference_unavailable"}


def record(session: Session, *, user_id: int, event_type: str, action_id: int | None = None,
           transfer_id: int | None = None, transaction_id: int | None = None,
           tool: str | None = None, risk_level: str | None = None,
           reasons: tuple[str, ...] = (), result: str | None = None,
           reason_code: str | None = None) -> AuditLog:
    if (event_type not in EVENTS or (tool is not None and tool not in TOOLS)
            or (result is not None and result not in RESULTS)
            or (risk_level is not None and risk_level not in {"green", "yellow", "red"})
            or any(reason not in REASONS for reason in reasons)
            or (reason_code is not None and reason_code not in FAILURE_REASONS)):
        raise ValueError("审计字段不在白名单内")
    # A later REST operation can be connected to the original chat through a real
    # owned action / transfer. Never infer a conversation for direct REST requests.
    transfer = None
    if transfer_id is not None:
        transfer = session.exec(select(TransferRequest).where(
            TransferRequest.id == transfer_id, TransferRequest.user_id == user_id)).first()
    elif action_id is not None:
        transfer = session.exec(select(TransferRequest).where(
            TransferRequest.action_id == action_id, TransferRequest.user_id == user_id)).first()
    if transfer is not None:
        transfer_id, action_id = transfer.id, transfer.action_id
    else:
        # Don't attach another user's guessed IDs to this user's audit trail.
        transfer_id = None
        if action_id is not None:
            from app.models import PendingAction
            action = session.get(PendingAction, action_id)
            if action is None or action.user_id != user_id:
                action_id = None
    conversation_id = conversation_context.get()
    if conversation_id is None and action_id is not None:
        conversation_id = session.exec(select(AuditLog.conversation_id).where(
            AuditLog.user_id == user_id, AuditLog.action_id == action_id,
            AuditLog.conversation_id.is_not(None)).order_by(AuditLog.id)).first()
    entry = AuditLog(user_id=user_id, request_id=request_context.get() or uuid4().hex,
                     conversation_id=conversation_id, action_id=action_id, transfer_id=transfer_id,
                     transaction_id=transaction_id, event_type=event_type, tool=tool,
                     risk_level=risk_level, reason_codes=",".join([*(REASONS[r] for r in reasons),
                                                                   *([reason_code] if reason_code else [])]) or None,
                     result=result)
    session.add(entry)
    session.flush()
    return entry


def record_separately(**fields) -> None:
    with Session(get_engine()) as session:
        record(session, **fields)
        session.commit()
