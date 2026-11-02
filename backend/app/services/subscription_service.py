"""Simulated subscriptions with yellow-confirmed cancellation."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.agent.registry import RiskLevel, ToolSpec
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    Account, PendingAction, Subscription, SubscriptionCancelRequest, Transaction,
)
from app.risk.engine import RiskDecision
from app.services.action_service import create_pending_action
from app.services.audit_service import record, record_separately, request_context
from app.services.redaction import mask_text
from app.services.vault import VaultError, resolve, create_subscription_token
from app.services.operation_service import (begin_write, bind_preparation, check_prepared_reference,
                                            find_preparation)

_CHINA = timezone(timedelta(hours=8))
_CANCEL_SPEC = ToolSpec(name="subscription_cancel", description="模拟取消订阅", parameters={},
                        risk=RiskLevel.YELLOW)
_FAILURE_CODES = {
    "订阅不可用": "subscription_unavailable",
    "订阅已取消": "subscription_unavailable",
    "取消订阅未确认、已取消或已过期": "not_authorized",
    "取消订阅动作不可用": "unavailable",
    "引用不可用": "reference_unavailable",
}


class SubscriptionError(Exception):
    pass


def _today():
    return utcnow().astimezone(_CHINA).date()


def _begin_locked(session: Session) -> None:
    begin_write(session, SubscriptionError, "当前订阅演示仅支持 SQLite")


def list_subscriptions(session: Session, user_id: int) -> list[dict]:
    today = _today()
    rows = session.exec(select(Subscription).where(
        Subscription.user_id == user_id).order_by(Subscription.next_charge_date, Subscription.id)).all()
    return [{"subscription_id": item.id, "merchant": mask_text(item.merchant),
             "amount_fen": item.amount_fen, "cycle": item.cycle,
             "next_charge_date": item.next_charge_date.isoformat(),
             "days_until_charge": (item.next_charge_date - today).days,
             "renewal_soon": (item.status == "active"
                              and 0 <= (item.next_charge_date - today).days <= 7),
             "status": item.status, "can_cancel": item.status == "active"}
            for item in rows]


def detect_candidates(session: Session, user_id: int, months: int = 6) -> list[dict]:
    cutoff = utcnow() - timedelta(days=max(months, 1) * 31)
    rows = session.exec(select(Transaction).join(
        Account, Transaction.account_id == Account.id).where(
        Account.user_id == user_id, Transaction.direction == "expense",
        Transaction.occurred_at >= cutoff,
        ~Transaction.category.in_(["模拟转账", "理财申购", "理财赎回"]))).all()
    # Periodicity must be proven within ONE account. Grouping only by
    # merchant + amount can create false candidates by combining payments
    # from different accounts on different months.
    grouped: dict[tuple[int, str, int], list[datetime]] = {}
    for entry in rows:
        grouped.setdefault(
            (entry.account_id, entry.counterparty, entry.amount_fen), [],
        ).append(entry.occurred_at)
    candidates = []
    for (_, merchant, amount_fen), times in grouped.items():
        times.sort()
        months_seen = {(item.year, item.month) for item in times}
        if len(times) < 2 or len(months_seen) < 2:
            continue
        candidates.append({"merchant": mask_text(merchant), "amount_fen": amount_fen,
                           "occurrences": len(times), "last_occurred_at": times[-1].isoformat(),
                           "suggested_cycle": "monthly"})
    candidates.sort(key=lambda item: item["last_occurred_at"], reverse=True)
    return candidates[:10]


def _subscription(session: Session, user_id: int, subscription_id: int) -> Subscription:
    item = session.exec(select(Subscription).where(
        Subscription.id == subscription_id, Subscription.user_id == user_id)).first()
    if item is None:
        raise SubscriptionError("订阅不可用")
    if item.status != "active":
        raise SubscriptionError("订阅已取消")
    return item


def _prepare_cancel(user_id: int, *, subscription_id: int | None = None,
                    subscription_token: str | None = None, model_request: bool = False,
                    idempotency_key: str | None = None) -> dict:
    with Session(get_engine()) as session:
        _begin_locked(session)
        scope = request_context.get() or uuid.uuid4().hex
        if model_request:
            if subscription_token is None:
                raise SubscriptionError("订阅不可用")
            subscription_id = resolve(session, user_id, subscription_token, "subscription", scope)
        if subscription_id is None:
            raise SubscriptionError("订阅不可用")
        existing = find_preparation(session, user_id, "subscription_cancel", idempotency_key,
                                     subscription_id, SubscriptionError)
        if existing is not None:
            session.commit()
            return {**existing, "subscription_id": subscription_id, "risk_level": "yellow",
                    "message": "请求已存在；确认令牌只在首次创建时返回。"}
        item = _subscription(session, user_id, subscription_id)
        subscription_token = subscription_token or create_subscription_token(session, user_id, item.id)
        decision = RiskDecision(RiskLevel.YELLOW, ("工具基础风险等级",))
        details = {"subscription_id": item.id, "merchant": mask_text(item.merchant),
                   "amount_fen": item.amount_fen, "cycle": item.cycle,
                   "next_charge_date": item.next_charge_date.isoformat(), "status": item.status}
        action, token = create_pending_action(
            session, user_id=user_id, action_type="subscription_cancel", details=details,
            decision=decision, commit=False)
        session.add(SubscriptionCancelRequest(user_id=user_id, subscription_id=item.id,
                                              action_id=action.id))
        bind_preparation(session, user_id, "subscription_cancel", idempotency_key,
                         item.id, action.id, subscription_token, scope)
        record(session, user_id=user_id, action_id=action.id, event_type="risk_assessed",
               tool=_CANCEL_SPEC.name, risk_level=decision.level.value,
               reasons=decision.reasons, result="success")
        record(session, user_id=user_id, action_id=action.id, event_type="subscription_cancel_prepared",
               tool="prepare_cancel_subscription", risk_level="yellow", result="success")
        session.commit()
        return {"action_id": action.id, "subscription_id": item.id, "risk_level": "yellow",
                "status": "pending", "confirmation_token": token,
                "message": "等待确认；尚未取消模拟订阅。"}


def _execute_cancel(user_id: int, action_id: int) -> dict:
    with Session(get_engine()) as session:
        _begin_locked(session)
        request = session.exec(select(SubscriptionCancelRequest).where(
            SubscriptionCancelRequest.action_id == action_id,
            SubscriptionCancelRequest.user_id == user_id)).first()
        if request is None:
            raise SubscriptionError("取消订阅动作不可用")
        item = session.get(Subscription, request.subscription_id)
        if item is None or item.user_id != user_id:
            raise SubscriptionError("订阅不可用")
        if request.status == "completed":
            record(session, user_id=user_id, action_id=action_id,
                   event_type="subscription_cancel_retried", tool=_CANCEL_SPEC.name,
                   result="retry")
            session.commit()
            return {"subscription_id": item.id, "status": "cancelled"}
        if item.status != "active":
            raise SubscriptionError("订阅已取消")
        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == "subscription_cancel",
            PendingAction.risk_level == RiskLevel.YELLOW.value,
            PendingAction.status == "confirmed", PendingAction.expires_at > now)).first()
        if action is None:
            raise SubscriptionError("取消订阅未确认、已取消或已过期")
        check_prepared_reference(session, user_id, "subscription_cancel", action_id,
                                 item.id, "subscription", item.id)
        item.status = "cancelled"
        item.updated_at = now
        request.status = "completed"
        action.status = "completed"
        session.add(item)
        session.add(request)
        session.add(action)
        record(session, user_id=user_id, action_id=action_id, event_type="subscription_cancelled",
               tool=_CANCEL_SPEC.name, risk_level="yellow", result="success")
        session.commit()
        return {"subscription_id": item.id, "status": "cancelled"}


def _record_failure(user_id: int, event_type: str, exc: Exception, *,
                    action_id: int | None = None) -> None:
    code = _FAILURE_CODES.get(str(exc), "unavailable" if isinstance(exc, SubscriptionError)
                              else "internal_error")
    record_separately(user_id=user_id, event_type=event_type, action_id=action_id,
                      result="denied" if isinstance(exc, SubscriptionError) else "failed",
                      reason_code=code)


def prepare_cancel(user_id: int, *, subscription_id: int | None = None,
                   subscription_token: str | None = None, model_request: bool = False,
                   idempotency_key: str | None = None) -> dict:
    try:
        return _prepare_cancel(user_id, subscription_id=subscription_id,
                               subscription_token=subscription_token, model_request=model_request,
                               idempotency_key=idempotency_key)
    except VaultError:
        record_separately(user_id=user_id, event_type="token_resolve_denied", result="denied",
                          reason_code="reference_unavailable")
        raise SubscriptionError("引用不可用") from None
    except Exception as exc:
        denied = isinstance(exc, SubscriptionError)
        _record_failure(user_id,
                        "subscription_cancel_prepare_denied" if denied
                        else "subscription_cancel_prepare_failed", exc)
        raise


def execute_cancel(user_id: int, action_id: int) -> dict:
    try:
        return _execute_cancel(user_id, action_id)
    except VaultError:
        record_separately(user_id=user_id, event_type="token_resolve_denied", result="denied",
                          reason_code="reference_unavailable")
        raise SubscriptionError("引用不可用") from None
    except Exception as exc:
        denied = isinstance(exc, SubscriptionError)
        _record_failure(user_id, "subscription_cancel_denied" if denied
                        else "subscription_cancel_failed", exc, action_id=action_id)
        raise
