from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import SecurityState
from app.services.audit_service import record


class SecurityError(Exception):
    pass


class SecurityLocked(SecurityError):
    pass


class SecurityRateLimited(SecurityError):
    pass


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _begin(session: Session) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))


def _state(session: Session, user_id: int) -> SecurityState:
    state = session.get(SecurityState, user_id)
    if state is None:
        now = utcnow()
        state = SecurityState(user_id=user_id, failure_window_started_at=now,
                              request_window_started_at=now)
        session.add(state)
        session.flush()
    return state


def _expire_lock(state: SecurityState, now: datetime) -> bool:
    locked = _aware(state.locked_until)
    if locked is None or locked > now:
        return False
    state.locked_until = None
    state.failure_count = 0
    state.failure_window_started_at = now
    return True


def check_request(user_id: int) -> None:
    with Session(get_engine()) as session:
        _begin(session)
        state = _state(session, user_id)
        now = utcnow()
        locked = _aware(state.locked_until)
        if locked is not None and locked > now:
            record(session, user_id=user_id, event_type="security_lock_denied",
                   result="denied", reason_code="account_locked")
            session.commit()
            raise SecurityLocked("账户因连续失败暂时锁定，请稍后再试或使用解锁流程。")
        if _expire_lock(state, now):
            record(session, user_id=user_id, event_type="security_unlocked",
                   result="success", reason_code="lock_expired")

        started = _aware(state.request_window_started_at)
        if started is None or now - started >= timedelta(seconds=settings.security_rate_window_seconds):
            state.request_window_started_at = now
            state.request_count = 0
        state.request_count += 1
        state.updated_at = now
        if state.request_count > settings.security_rate_limit_requests:
            record(session, user_id=user_id, event_type="security_rate_limited",
                   result="denied", reason_code="rate_limit")
            session.add(state)
            session.commit()
            raise SecurityRateLimited("请求过于频繁，请稍后再试。")
        session.add(state)
        session.commit()


def record_failure(user_id: int) -> None:
    with Session(get_engine()) as session:
        _begin(session)
        state = _state(session, user_id)
        now = utcnow()
        locked = _aware(state.locked_until)
        if locked is not None and locked > now:
            session.commit()
            return
        if _expire_lock(state, now):
            record(session, user_id=user_id, event_type="security_unlocked",
                   result="success", reason_code="lock_expired")

        started = _aware(state.failure_window_started_at)
        if started is None or now - started >= timedelta(seconds=settings.security_failure_window_seconds):
            state.failure_window_started_at = now
            state.failure_count = 1
        else:
            state.failure_count += 1
        state.updated_at = now
        record(session, user_id=user_id, event_type="security_failure",
               result="failed", reason_code="failure")
        if state.failure_count >= settings.security_failure_threshold:
            state.locked_until = now + timedelta(seconds=settings.security_lock_seconds)
            record(session, user_id=user_id, event_type="security_locked",
                   result="locked", reason_code="failure_threshold")
        session.add(state)
        session.commit()


def unlock_user(user_id: int) -> None:
    with Session(get_engine()) as session:
        _begin(session)
        state = _state(session, user_id)
        now = utcnow()
        state.locked_until = None
        state.failure_count = 0
        state.failure_window_started_at = now
        state.updated_at = now
        record(session, user_id=user_id, event_type="security_unlocked",
               result="success", reason_code="manual_unlock")
        session.add(state)
        session.commit()


def is_locked(user_id: int) -> bool:
    with Session(get_engine()) as session:
        state = session.get(SecurityState, user_id)
        locked = _aware(state.locked_until) if state is not None else None
        return locked is not None and locked > utcnow()
