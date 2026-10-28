import hashlib
import json
import secrets
from datetime import timedelta, timezone

from sqlalchemy import update
from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.time import utcnow
from app.models import PendingAction
from app.risk.engine import RiskDecision
from app.services.audit_service import record
from app.services.security_service import record_failure


def create_pending_action(
    session: Session, *, user_id: int, action_type: str, details: dict,
    decision: RiskDecision, expires_in_seconds: int = 300, commit: bool = True,
) -> tuple[PendingAction, str]:
    """Internal server-side entry point; only yellow decisions can be confirmed here."""
    if decision.level != RiskLevel.YELLOW:
        raise ValueError("仅需确认的黄色操作可创建待确认动作")
    if (not action_type or not isinstance(details, dict) or type(expires_in_seconds) is not int
            or not 1 <= expires_in_seconds <= 3600):
        raise ValueError("待确认动作参数无效")
    token = secrets.token_urlsafe(32)
    action = PendingAction(
        user_id=user_id, action_type=action_type,
        details_json=json.dumps(details, ensure_ascii=False), risk_level=decision.level.value,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=utcnow() + timedelta(seconds=expires_in_seconds),
    )
    session.add(action)
    session.flush()
    if commit:
        session.commit()
        session.refresh(action)
    return action, token


def create_simulated_red_action(
    session: Session, *, user_id: int, action_type: str, details: dict,
    decision: RiskDecision, expires_in_seconds: int = 300, commit: bool = True,
) -> tuple[PendingAction, str]:
    """Create a red action only for isolated demo verification; never executes it."""
    from app.core.config import settings

    if not settings.debug or decision.level != RiskLevel.RED:
        raise ValueError("模拟强验证不可用")
    if (not action_type or not isinstance(details, dict) or type(expires_in_seconds) is not int
            or not 1 <= expires_in_seconds <= 3600):
        raise ValueError("待验证动作参数无效")
    token = secrets.token_urlsafe(32)
    action = PendingAction(
        user_id=user_id, action_type=action_type,
        details_json=json.dumps(details, ensure_ascii=False), risk_level=RiskLevel.RED.value,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=utcnow() + timedelta(seconds=expires_in_seconds),
    )
    session.add(action)
    session.flush()
    if commit:
        session.commit()
        session.refresh(action)
    return action, token


def confirm_pending_action(session: Session, *, user_id: int, action_id: int, token: str) -> bool:
    """Atomically consume a user's unexpired, single-use confirmation token."""
    now = utcnow()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = session.execute(
        update(PendingAction).where(
            PendingAction.id == action_id,
            PendingAction.user_id == user_id,
            PendingAction.status == "pending",
            PendingAction.risk_level == RiskLevel.YELLOW.value,
            PendingAction.expires_at > now,
            PendingAction.token_hash == token_hash,
        ).values(status="confirmed", confirmed_at=now)
    )
    success = result.rowcount == 1
    record(session, user_id=user_id, action_id=action_id,
           event_type="action_confirmed" if success else "action_confirm_denied",
           result="success" if success else "denied")
    session.commit()
    if not success:
        record_failure(user_id)
    return success


def get_pending_action(session: Session, *, user_id: int, action_id: int) -> dict | None:
    action = session.exec(select(PendingAction).where(
        PendingAction.id == action_id, PendingAction.user_id == user_id,
    )).first()
    if action is None:
        return None
    expires_at = action.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    status = action.status
    if status == "pending" and expires_at <= utcnow():
        status = "expired"
    return {
        "id": action.id, "action_type": action.action_type,
        "details": json.loads(action.details_json), "risk_level": action.risk_level,
        "status": status, "created_at": action.created_at, "expires_at": expires_at,
        "confirmed_at": action.confirmed_at,
    }


def cancel_pending_action(session: Session, *, user_id: int, action_id: int) -> bool:
    """Cancel only a still-pending, unexpired action, atomically with confirmation."""
    result = session.execute(update(PendingAction).where(
        PendingAction.id == action_id,
        PendingAction.user_id == user_id,
        PendingAction.status == "pending",
        PendingAction.expires_at > utcnow(),
    ).values(status="cancelled"))
    success = result.rowcount == 1
    record(session, user_id=user_id, action_id=action_id,
           event_type="action_cancelled" if success else "action_cancel_denied",
           result="success" if success else "denied")
    session.commit()
    return success
