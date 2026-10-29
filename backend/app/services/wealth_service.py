"""Simulated wealth products with red-verified subscribe and redeem orders."""
import uuid
from datetime import timezone

from sqlmodel import Session, select

from app.agent.registry import RiskLevel, ToolSpec
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    Account, Card, DataToken, PendingAction, Transaction, VerificationSession,
    WealthHolding, WealthOrder, WealthProduct, WealthRiskProfile,
)
from app.risk.engine import assess_tool
from app.schemas.wealth import PrepareWealthRedeemRequest, PrepareWealthSubscribeRequest
from app.services.action_service import create_simulated_red_action, get_pending_action
from app.services.audit_service import record, record_separately, request_context
from app.services.redaction import mask_text
from app.services.operation_service import begin_write
from app.services.vault import VaultError, create_account_token, create_product_token, resolve

_SUBSCRIBE_SPEC = ToolSpec(name="wealth_subscribe", description="模拟理财申购", parameters={}, risk=RiskLevel.RED)
_REDEEM_SPEC = ToolSpec(name="wealth_redeem", description="模拟理财赎回", parameters={}, risk=RiskLevel.RED)
_FAILURE_CODES = {
    "理财产品不可用": "product_unavailable",
    "持仓不足": "insufficient_holding",
    "申购金额低于起购金额": "amount_invalid",
    "账户币种不支持或余额不足": "insufficient_balance",
    "理财操作尚未通过有效的模拟验证": "not_authorized",
    "请求编号已用于其他理财操作": "duplicate_mismatch",
    "红色操作暂不支持真实验证": "verification_unavailable",
    "理财操作不存在": "unavailable",
    "待验证动作不可用": "not_authorized",
    "账户不存在或不可用": "unavailable",
    "请先指定操作账户": "amount_invalid",
    "关联卡片不可用，无法申购": "unavailable",
}


class WealthError(Exception):
    pass


def _begin_locked(session: Session) -> None:
    begin_write(session, WealthError, "当前理财演示仅支持 SQLite")


def _account_for(session: Session, user_id: int, account_id: int | None) -> Account:
    if account_id is None:
        accounts = session.exec(select(Account).where(
            Account.user_id == user_id, Account.status == "active")).all()
        if len(accounts) != 1:
            raise WealthError("请先指定操作账户")
        return accounts[0]
    account = session.exec(select(Account).where(
        Account.id == account_id, Account.user_id == user_id)).first()
    if account is None or account.status != "active":
        raise WealthError("账户不存在或不可用")
    return account


def _product(session: Session, product_id: int) -> WealthProduct:
    product = session.get(WealthProduct, product_id)
    if product is None or product.status != "available":
        raise WealthError("理财产品不可用")
    return product


def _holding_for(session: Session, user_id: int, product_id: int) -> WealthHolding | None:
    return session.exec(select(WealthHolding).where(
        WealthHolding.user_id == user_id, WealthHolding.product_id == product_id)).first()


def _require_card_available(session: Session, account_id: int) -> None:
    card = session.exec(select(Card).where(Card.account_id == account_id)).first()
    if card is None or card.status != "active":
        raise WealthError("关联卡片不可用，无法申购")


def get_risk_profile(session: Session, user_id: int) -> dict:
    profile = session.get(WealthRiskProfile, user_id)
    if profile is None:
        return {"risk_level": "未评估", "score": 0, "assessed_at": None}
    assessed = profile.assessed_at
    if assessed.tzinfo is None:
        assessed = assessed.replace(tzinfo=timezone.utc)
    return {"risk_level": profile.risk_level, "score": profile.score,
            "assessed_at": assessed.isoformat()}


def assess_risk(user_id: int, answers: list[int]) -> dict:
    if (len(answers) != 3 or any(type(item) is not int or not 0 <= item <= 3 for item in answers)):
        raise WealthError("风险测评参数无效")
    score = sum(answers)
    risk_level = ("R1" if score <= 2 else "R2" if score <= 5 else "R3" if score <= 7 else "R4")
    with Session(get_engine()) as session:
        profile = session.get(WealthRiskProfile, user_id)
        if profile is None:
            profile = WealthRiskProfile(user_id=user_id)
        profile.risk_level = risk_level
        profile.score = score
        profile.assessed_at = utcnow()
        session.add(profile)
        record(session, user_id=user_id, event_type="wealth_risk_assessed", result="success")
        session.commit()
        assessed = profile.assessed_at
        if assessed.tzinfo is None:
            assessed = assessed.replace(tzinfo=timezone.utc)
        return {"risk_level": risk_level, "score": score, "assessed_at": assessed.isoformat(),
                "message": "风险测评已保存。"}


def list_products(session: Session, user_id: int) -> list[dict]:
    products = session.exec(select(WealthProduct).where(
        WealthProduct.status == "available").order_by(WealthProduct.id)).all()
    return [{"product_id": product.id, "name": mask_text(product.name),
             "category": mask_text(product.category), "risk_level": product.risk_level,
             "expected_rate_bps": product.expected_rate_bps, "term_days": product.term_days,
             "min_amount_fen": product.min_amount_fen, "status": product.status}
            for product in products]


def list_holdings(session: Session, user_id: int) -> list[dict]:
    rows = session.exec(select(WealthHolding, WealthProduct).join(
        WealthProduct, WealthHolding.product_id == WealthProduct.id).where(
        WealthHolding.user_id == user_id).order_by(WealthHolding.id)).all()
    return [{"holding_id": holding.id, "product_id": product.id,
             "product_name": mask_text(product.name), "category": mask_text(product.category),
             "risk_level": product.risk_level, "expected_rate_bps": product.expected_rate_bps,
             "amount_fen": holding.amount_fen,
             "yesterday_earnings_fen": holding.yesterday_earnings_fen,
             "status": holding.status}
            for holding, product in rows]


def _prepare_order(user_id: int, payload: PrepareWealthSubscribeRequest | PrepareWealthRedeemRequest,
                   order_type: str, *, product_token: str | None = None,
                   account_token: str | None = None, model_request: bool = False) -> dict:
    with Session(get_engine()) as session:
        _begin_locked(session)
        if not settings.debug:
            raise WealthError("红色操作暂不支持真实验证")
        scope = request_context.get() or uuid.uuid4().hex
        if model_request:
            if product_token is None:
                raise WealthError("理财产品不可用")
            product_id = resolve(session, user_id, product_token, "product", scope)
            account_id = resolve(session, user_id, account_token, "account", scope) if account_token else None
        else:
            product_id, account_id = payload.product_id, payload.account_id
        product = _product(session, product_id)
        account = _account_for(session, user_id, account_id)
        if account.currency != "CNY":
            raise WealthError("账户币种不支持或余额不足")
        note = mask_text(payload.note)
        existing = session.exec(select(WealthOrder).where(
            WealthOrder.user_id == user_id,
            WealthOrder.idempotency_key == payload.idempotency_key)).first()
        if existing is not None:
            if (existing.order_type != order_type or existing.account_id != account.id
                    or existing.product_id != product.id or existing.amount_fen != payload.amount_fen
                    or existing.note != note):
                raise WealthError("请求编号已用于其他理财操作")
            action = get_pending_action(session, user_id=user_id, action_id=existing.action_id)
            if action is None:
                raise WealthError("待验证动作不可用")
            record(session, user_id=user_id, action_id=existing.action_id,
                   event_type="wealth_order_prepare_retried",
                   tool=f"prepare_wealth_{order_type}", result="retry")
            session.commit()
            return {"order_id": existing.id, "action_id": existing.action_id, "risk_level": "red",
                    "status": action["status"], "confirmation_token": None,
                    "message": "请求已存在；确认令牌只在首次创建时返回。"}

        if order_type == "subscribe":
            _require_card_available(session, account.id)
            if payload.amount_fen < product.min_amount_fen:
                raise WealthError("申购金额低于起购金额")
            if account.balance_fen < payload.amount_fen:
                raise WealthError("账户币种不支持或余额不足")
        else:
            holding = _holding_for(session, user_id, product.id)
            if holding is None or holding.amount_fen < payload.amount_fen:
                raise WealthError("持仓不足")

        if model_request:
            account_token = account_token or create_account_token(session, user_id, account.id)
            product_token = product_token or create_product_token(session, user_id, product.id)
        else:
            account_token = create_account_token(session, user_id, account.id)
            product_token = create_product_token(session, user_id, product.id)
        account_row = session.exec(select(DataToken).where(
            DataToken.token == account_token, DataToken.user_id == user_id)).first()
        product_row = session.exec(select(DataToken).where(
            DataToken.token == product_token, DataToken.user_id == user_id)).first()
        if account_row is None or product_row is None:
            raise VaultError()

        spec = _SUBSCRIBE_SPEC if order_type == "subscribe" else _REDEEM_SPEC
        decision = assess_tool(spec)
        details = {"order_type": order_type, "product_id": product.id,
                   "product_name": mask_text(product.name), "product_category": mask_text(product.category),
                   "product_risk_level": product.risk_level,
                   "expected_rate_bps": product.expected_rate_bps, "term_days": product.term_days,
                   "account_id": account.id, "account_masked": mask_text(account.masked_number),
                   "amount_fen": payload.amount_fen, "note": note, "currency": "CNY"}
        action, token = create_simulated_red_action(
            session, user_id=user_id, action_type=f"wealth_{order_type}", details=details,
            decision=decision, commit=False)
        order = WealthOrder(user_id=user_id, account_id=account.id, product_id=product.id,
                            action_id=action.id, idempotency_key=payload.idempotency_key,
                            order_type=order_type, amount_fen=payload.amount_fen, note=note,
                            account_token_id=account_row.id, product_token_id=product_row.id,
                            request_scope=scope)
        session.add(order)
        session.flush()
        record(session, user_id=user_id, action_id=action.id, event_type="risk_assessed",
               tool=spec.name, risk_level=decision.level.value, reasons=decision.reasons, result="success")
        record(session, user_id=user_id, action_id=action.id, event_type="wealth_order_prepared",
               tool=f"prepare_wealth_{order_type}", risk_level=decision.level.value, result="success")
        session.commit()
        return {"order_id": order.id, "action_id": action.id, "risk_level": "red",
                "status": "pending", "confirmation_token": token,
                "message": "等待模拟验证码验证；尚未执行模拟理财操作。"}


def _execute_order(user_id: int, order_id: int) -> dict:
    with Session(get_engine()) as session:
        _begin_locked(session)
        order = session.exec(select(WealthOrder).where(
            WealthOrder.id == order_id, WealthOrder.user_id == user_id)).first()
        if order is None:
            raise WealthError("理财操作不存在")
        if order.order_type not in {"subscribe", "redeem"}:
            raise WealthError("理财操作不存在")
        spec = _SUBSCRIBE_SPEC if order.order_type == "subscribe" else _REDEEM_SPEC
        if order.status == "completed":
            if (order.transaction_id is None or order.balance_after_fen is None
                    or order.holding_after_fen is None):
                raise WealthError("理财操作不存在")
            record(session, user_id=user_id, action_id=order.action_id,
                   event_type="wealth_order_retried", tool=spec.name, result="retry")
            session.commit()
            return {"order_id": order.id, "order_type": order.order_type, "status": "completed",
                    "transaction_id": order.transaction_id, "balance_fen": order.balance_after_fen,
                    "holding_fen": order.holding_after_fen}

        if not settings.debug:
            raise WealthError("红色操作暂不支持真实验证")
        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == order.action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == f"wealth_{order.order_type}",
            PendingAction.risk_level == RiskLevel.RED.value,
            PendingAction.status == "verified", PendingAction.expires_at > now)).first()
        verification = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == order.action_id,
            VerificationSession.user_id == user_id, VerificationSession.status == "verified",
            VerificationSession.expires_at > now)).first()
        if action is None or verification is None:
            raise WealthError("理财操作尚未通过有效的模拟验证")

        account_row = session.get(DataToken, order.account_token_id)
        product_row = session.get(DataToken, order.product_token_id)
        if account_row is None or product_row is None:
            raise VaultError()
        account_id = resolve(session, user_id, account_row.token, "account", order.request_scope)
        product_id = resolve(session, user_id, product_row.token, "product", order.request_scope)
        if account_id != order.account_id or product_id != order.product_id:
            raise VaultError()

        account = _account_for(session, user_id, account_id)
        if account.currency != "CNY":
            raise WealthError("账户币种不支持或余额不足")
        product = _product(session, product_id)
        holding = _holding_for(session, user_id, product_id)
        if order.order_type == "subscribe":
            _require_card_available(session, account.id)
            if account.balance_fen < order.amount_fen:
                raise WealthError("账户币种不支持或余额不足")
            if holding is None:
                holding = WealthHolding(user_id=user_id, product_id=product_id, amount_fen=0)
                session.add(holding)
                session.flush()
            holding.amount_fen += order.amount_fen
            holding.status = "active"
            account.balance_fen -= order.amount_fen
            direction, category = "expense", "理财申购"
        else:
            if holding is None or holding.amount_fen < order.amount_fen:
                raise WealthError("持仓不足")
            the_original = holding.amount_fen
            holding.amount_fen -= order.amount_fen
            if the_original > 0:
                holding.yesterday_earnings_fen = (
                    holding.yesterday_earnings_fen * holding.amount_fen // the_original)
            holding.status = "active" if holding.amount_fen > 0 else "redeemed"
            account.balance_fen += order.amount_fen
            direction, category = "income", "理财赎回"

        holding.updated_at = now
        account.updated_at = now
        transaction = Transaction(account_id=account.id, reference=f"wealth-{uuid.uuid4().hex}",
                                  direction=direction, amount_fen=order.amount_fen,
                                  balance_after_fen=account.balance_fen,
                                  counterparty=mask_text(product.name), category=category,
                                  note=order.note, occurred_at=now)
        session.add(account)
        session.add(holding)
        session.add(transaction)
        session.flush()
        order.status = "completed"
        order.transaction_id = transaction.id
        order.holding_id = holding.id
        order.balance_after_fen = account.balance_fen
        order.holding_after_fen = holding.amount_fen
        order.completed_at = now
        action.status = "completed"
        session.add(order)
        session.add(action)
        record(session, user_id=user_id, action_id=action.id, event_type="wealth_order_completed",
               tool=spec.name, risk_level=RiskLevel.RED.value, result="success")
        session.commit()
        return {"order_id": order.id, "order_type": order.order_type, "status": "completed",
                "transaction_id": transaction.id, "balance_fen": account.balance_fen,
                "holding_fen": holding.amount_fen}


def _record_failure(user_id: int, event_type: str, exc: Exception,
                    *, order_id: int | None = None) -> None:
    code = _FAILURE_CODES.get(str(exc), "unavailable" if isinstance(exc, WealthError) else "internal_error")
    action_id = None
    if order_id is not None:
        with Session(get_engine()) as session:
            order = session.get(WealthOrder, order_id)
            if order is not None and order.user_id == user_id:
                action_id = order.action_id
    record_separately(user_id=user_id, event_type=event_type, action_id=action_id,
                      result="denied" if isinstance(exc, WealthError) else "failed", reason_code=code)


def prepare_subscribe(user_id: int, payload: PrepareWealthSubscribeRequest, *,
                      product_token: str | None = None, account_token: str | None = None,
                      model_request: bool = False) -> dict:
    try:
        return _prepare_order(user_id, payload, "subscribe", product_token=product_token,
                              account_token=account_token, model_request=model_request)
    except VaultError:
        record_separately(user_id=user_id, event_type="token_resolve_denied", result="denied",
                          reason_code="reference_unavailable")
        raise WealthError("引用不可用") from None
    except Exception as exc:
        denied = isinstance(exc, WealthError)
        _record_failure(user_id, "wealth_order_prepare_denied" if denied else "wealth_order_prepare_failed", exc)
        raise


def prepare_redeem(user_id: int, payload: PrepareWealthRedeemRequest, *,
                   product_token: str | None = None, account_token: str | None = None,
                   model_request: bool = False) -> dict:
    try:
        return _prepare_order(user_id, payload, "redeem", product_token=product_token,
                              account_token=account_token, model_request=model_request)
    except VaultError:
        record_separately(user_id=user_id, event_type="token_resolve_denied", result="denied",
                          reason_code="reference_unavailable")
        raise WealthError("引用不可用") from None
    except Exception as exc:
        denied = isinstance(exc, WealthError)
        _record_failure(user_id, "wealth_order_prepare_denied" if denied else "wealth_order_prepare_failed", exc)
        raise


def execute_order(user_id: int, order_id: int) -> dict:
    try:
        return _execute_order(user_id, order_id)
    except VaultError:
        record_separately(user_id=user_id, event_type="token_resolve_denied", result="denied",
                          reason_code="reference_unavailable")
        raise WealthError("引用不可用") from None
    except Exception as exc:
        denied = isinstance(exc, WealthError)
        _record_failure(user_id, "wealth_order_denied" if denied else "wealth_order_failed", exc,
                        order_id=order_id)
        raise
