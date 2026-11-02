import hashlib
import hmac
import json
from datetime import timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import PendingAction, VerificationSession
from app.services.audit_service import record, record_separately
from app.services.security_service import record_failure

MAX_ATTEMPTS = 3


class VerificationError(Exception):
    pass


def _begin(session: Session) -> None:
    if not settings.debug or session.get_bind().dialect.name != "sqlite":
        raise VerificationError("模拟验证不可用")
    session.execute(text("BEGIN IMMEDIATE"))


def _action(session: Session, user_id: int, action_id: int, token: str) -> PendingAction:
    action = session.exec(select(PendingAction).where(
        PendingAction.id == action_id, PendingAction.user_id == user_id,
        PendingAction.risk_level == RiskLevel.RED.value, PendingAction.status == "pending",
        PendingAction.expires_at > utcnow(),
    )).first()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if action is None or not hmac.compare_digest(action.token_hash, digest):
        raise VerificationError("验证失败：动作无效、已处理或已过期")
    return action


def _requires_face(action: PendingAction) -> bool:
    try:
        details = json.loads(action.details_json)
    except (TypeError, ValueError):
        return False
    return isinstance(details, dict) and details.get("verification") == "password_face"


def _code_digest(action_id: int, code: str) -> str:
    message = f"{action_id}:{code}".encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _start_verification(user_id: int, action_id: int, token: str) -> None:
    with Session(get_engine()) as session:
        _begin(session)
        action = _action(session, user_id, action_id, token)
        existing = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == action_id,
        )).first()
        if existing is not None:
            expiry = existing.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if existing.status != "pending" or expiry <= utcnow():
                raise VerificationError("验证不可用，请重新发起操作")
            record(session, user_id=user_id, action_id=action_id, event_type="verification_started", result="retry")
            session.commit()
            return
        action_expiry = action.expires_at
        if action_expiry.tzinfo is None:
            action_expiry = action_expiry.replace(tzinfo=timezone.utc)
        verification = VerificationSession(
            action_id=action_id, user_id=user_id,
            code_digest=_code_digest(action_id, settings.demo_verification_code),
            expires_at=min(action_expiry, utcnow() + timedelta(minutes=5)),
        )
        session.add(verification)
        record(session, user_id=user_id, action_id=action_id, event_type="verification_started", result="success")
        session.commit()


def _verify_code(user_id: int, action_id: int, token: str, code: str) -> bool:
    """Check demo code atomically, limiting attempts across concurrent requests."""
    with Session(get_engine()) as session:
        _begin(session)
        action = _action(session, user_id, action_id, token)
        verification = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == action_id, VerificationSession.user_id == user_id,
            VerificationSession.status == "pending", VerificationSession.expires_at > utcnow(),
        )).first()
        if verification is None:
            raise VerificationError("验证不可用，请重新发起操作")
        if not hmac.compare_digest(verification.code_digest, _code_digest(action_id, code)):
            verification.attempts += 1
            if verification.attempts >= MAX_ATTEMPTS:
                verification.status = "locked"
            session.add(verification)
            locked = verification.status == "locked"
            record(session, user_id=user_id, action_id=action_id,
                   event_type="verification_locked" if locked else "verification_failed",
                   result="locked" if locked else "failed")
            session.commit()
            return False
        now = utcnow()
        if _requires_face(action):
            verification.status = "code_verified"
            action.status = "pending"
            outcome = "code_verified"
        else:
            verification.status = "verified"
            verification.verified_at = now
            action.status = "verified"
            outcome = "verified"
        session.add(verification)
        session.add(action)
        record(session, user_id=user_id, action_id=action_id, event_type="verification_succeeded", result="success")
        session.commit()
        return outcome


def _verify_face(user_id: int, action_id: int, token: str) -> None:
    with Session(get_engine()) as session:
        _begin(session)
        action = _action(session, user_id, action_id, token)
        if not _requires_face(action):
            raise VerificationError("该操作不需要人脸验证")
        verification = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == action_id, VerificationSession.user_id == user_id,
            VerificationSession.status == "code_verified", VerificationSession.expires_at > utcnow(),
        )).first()
        if verification is None:
            raise VerificationError("验证码尚未通过或验证已过期")
        now = utcnow()
        verification.status = "verified"
        verification.verified_at = now
        action.status = "verified"
        session.add(verification)
        session.add(action)
        record(session, user_id=user_id, action_id=action_id,
               event_type="verification_succeeded", result="success")
        session.commit()


def start_verification(user_id: int, action_id: int, token: str) -> None:
    try:
        return _start_verification(user_id, action_id, token)
    except Exception as exc:
        denied = isinstance(exc, VerificationError)
        record_separately(user_id=user_id, action_id=action_id,
                          event_type="verification_start_denied" if denied else "verification_start_failed",
                          result="denied" if denied else "failed")
        raise


def verify_code(user_id: int, action_id: int, token: str, code: str) -> str | bool:
    try:
        outcome = _verify_code(user_id, action_id, token, code)
    except Exception as exc:
        denied = isinstance(exc, VerificationError)
        record_separately(user_id=user_id, action_id=action_id,
                          event_type="verification_denied" if denied else "verification_error",
                          result="denied" if denied else "failed")
        raise
    if not outcome:
        record_failure(user_id)
    return outcome


def verify_face(user_id: int, action_id: int, token: str) -> None:
    try:
        _verify_face(user_id, action_id, token)
    except Exception as exc:
        denied = isinstance(exc, VerificationError)
        record_separately(user_id=user_id, action_id=action_id,
                          event_type="verification_denied" if denied else "verification_error",
                          result="denied" if denied else "failed")
        raise
