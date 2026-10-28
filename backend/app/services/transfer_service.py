import hashlib
import hmac
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, text
from sqlmodel import Session, select

from app.agent.registry import RiskLevel, ToolSpec
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, PendingAction, Transaction, TransferRequest, VerificationSession
from app.risk.engine import assess_tool
from app.schemas.transfers import PrepareTransferRequest
from app.services.action_service import create_pending_action, create_simulated_red_action, get_pending_action
from app.services.audit_service import record

_TRANSFER_SPEC = ToolSpec(name="transfer", description="模拟转账", parameters={}, risk=RiskLevel.YELLOW)
_CHINA = timezone(timedelta(hours=8))


class TransferError(Exception):
    def __init__(self, message: str, decision=None):
        super().__init__(message)
        self.decision = decision


def _begin_locked(session: Session) -> None:
    if session.get_bind().dialect.name != "sqlite":
        raise TransferError("当前转账演示仅支持 SQLite")
    session.execute(text("BEGIN IMMEDIATE"))


def _daily_total(session: Session, user_id: int, now: datetime) -> int:
    local_date = now.astimezone(_CHINA).date()
    start = datetime.combine(local_date, time.min, _CHINA).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    return session.exec(select(func.coalesce(func.sum(TransferRequest.amount_fen), 0)).where(
        TransferRequest.user_id == user_id, TransferRequest.status == "completed",
        TransferRequest.completed_at >= start, TransferRequest.completed_at < end,
    )).one()


def _phone_digest(phone: str | None) -> str | None:
    if phone is None:
        return None
    return hmac.new(settings.jwt_secret.encode("utf-8"), phone.encode("utf-8"), hashlib.sha256).hexdigest()


def _prepare_transfer(user_id: int, payload: PrepareTransferRequest) -> dict:
    """Prepare a simulated transfer; never trust a model's risk or daily total."""
    with Session(get_engine()) as session:
        _begin_locked(session)
        existing = session.exec(select(TransferRequest).where(
            TransferRequest.user_id == user_id,
            TransferRequest.idempotency_key == payload.idempotency_key,
        )).first()
        digest = _phone_digest(payload.recipient_phone)
        if existing:
            if (existing.account_id != payload.account_id or existing.amount_fen != payload.amount_fen
                    or existing.recipient_name != payload.recipient_name or existing.note != payload.note
                    or existing.recipient_phone_digest != digest):
                raise TransferError("请求编号已用于其他转账")
            action = get_pending_action(session, user_id=user_id, action_id=existing.action_id)
            if action is None:
                raise TransferError("待确认动作不可用")
            current_status = existing.status if existing.status == "completed" else action["status"]
            record(session, user_id=user_id, event_type="transfer_prepare_retried", transfer_id=existing.id,
                   tool="prepare_transfer", result="retry")
            session.commit()
            return {"transfer_id": existing.id, "action_id": existing.action_id,
                    "risk_level": action["risk_level"], "status": current_status, "confirmation_token": None,
                    "message": "请求已存在；确认令牌只在首次创建时返回。"}

        account = session.exec(select(Account).where(
            Account.id == payload.account_id, Account.user_id == user_id,
        )).first()
        if account is None or account.status != "active":
            raise TransferError("账户不存在或不可用")
        if account.currency != "CNY" or account.balance_fen < payload.amount_fen:
            raise TransferError("账户币种不支持或余额不足")
        now = utcnow()
        decision = assess_tool(_TRANSFER_SPEC, now=now, amount_fen=payload.amount_fen,
                               daily_total_fen=_daily_total(session, user_id, now))
        if decision.level == RiskLevel.RED and not settings.debug:
            raise TransferError("红色操作暂不支持真实验证", decision)
        if decision.level not in (RiskLevel.YELLOW, RiskLevel.RED):
            raise TransferError("转账风险等级无效")
        phone_masked = (payload.recipient_phone[:3] + "****" + payload.recipient_phone[-4:]
                        if payload.recipient_phone else None)
        details = {"account_id": account.id, "account_masked": account.masked_number,
                   "recipient_name": payload.recipient_name, "recipient_phone_masked": phone_masked,
                   "amount_fen": payload.amount_fen, "note": payload.note, "currency": "CNY"}
        create_action = create_simulated_red_action if decision.level == RiskLevel.RED else create_pending_action
        action, token = create_action(session, user_id=user_id, action_type="transfer",
                                      details=details, decision=decision, commit=False)
        transfer = TransferRequest(user_id=user_id, account_id=account.id, action_id=action.id,
                                   idempotency_key=payload.idempotency_key,
                                   recipient_name=payload.recipient_name,
                                   recipient_phone_masked=phone_masked, recipient_phone_digest=digest,
                                   amount_fen=payload.amount_fen, note=payload.note)
        session.add(transfer)
        session.flush()
        record(session, user_id=user_id, event_type="risk_assessed", action_id=action.id,
               transfer_id=transfer.id, tool="transfer", risk_level=decision.level.value,
               reasons=decision.reasons, result="success")
        record(session, user_id=user_id, event_type="transfer_prepared", action_id=action.id,
               transfer_id=transfer.id, tool="prepare_transfer", risk_level=decision.level.value, result="success")
        session.commit()
        message = ("等待模拟验证码验证；尚未执行模拟转账。" if decision.level == RiskLevel.RED
                   else "等待确认；尚未执行模拟转账。")
        return {"transfer_id": transfer.id, "action_id": action.id, "risk_level": decision.level.value,
                "status": "pending", "confirmation_token": token, "message": message}


def _execute_transfer(user_id: int, transfer_id: int) -> dict:
    """Serialize risk re-check, balance change and ledger write in one SQLite transaction."""
    with Session(get_engine()) as session:
        _begin_locked(session)
        transfer = session.exec(select(TransferRequest).where(
            TransferRequest.id == transfer_id, TransferRequest.user_id == user_id,
        )).first()
        if transfer is None:
            raise TransferError("转账不存在")
        if transfer.status == "completed":
            transaction = session.get(Transaction, transfer.transaction_id)
            if transaction is None:
                raise TransferError("转账记录不可用")
            record(session, user_id=user_id, event_type="transfer_retried", transfer_id=transfer.id,
                   transaction_id=transaction.id, tool="transfer", result="retry")
            session.commit()
            return {"transfer_id": transfer.id, "transaction_id": transaction.id,
                    "balance_fen": transaction.balance_after_fen}

        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == transfer.action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == "transfer", PendingAction.expires_at > now,
        )).first()
        if action is None:
            raise TransferError("转账未确认、未验证、已取消或已过期")
        if action.risk_level == RiskLevel.YELLOW.value:
            if action.status != "confirmed":
                raise TransferError("转账未确认、已取消或已过期")
        elif action.risk_level == RiskLevel.RED.value:
            if not settings.debug or action.status != "verified":
                raise TransferError("红色转账尚未通过模拟验证")
            verification = session.exec(select(VerificationSession).where(
                VerificationSession.action_id == action.id, VerificationSession.user_id == user_id,
                VerificationSession.status == "verified", VerificationSession.expires_at > now,
            )).first()
            if verification is None:
                raise TransferError("模拟验证无效或已过期")
        else:
            raise TransferError("转账风险等级无效")
        account = session.exec(select(Account).where(
            Account.id == transfer.account_id, Account.user_id == user_id,
        )).first()
        if account is None or account.status != "active" or account.currency != "CNY":
            raise TransferError("账户不存在或不可用")
        if account.balance_fen < transfer.amount_fen:
            raise TransferError("账户余额不足")
        decision = assess_tool(_TRANSFER_SPEC, now=now, amount_fen=transfer.amount_fen,
                               daily_total_fen=_daily_total(session, user_id, now))
        if decision.level not in (RiskLevel.YELLOW, RiskLevel.RED):
            raise TransferError("转账风险等级无效")
        if decision.level == RiskLevel.RED and action.risk_level != RiskLevel.RED.value:
            raise TransferError("风险已升级，请重新发起并完成模拟验证", decision)
        record(session, user_id=user_id, event_type="risk_assessed", transfer_id=transfer.id,
               tool="transfer", risk_level=decision.level.value, reasons=decision.reasons, result="success")
        account.balance_fen -= transfer.amount_fen
        account.updated_at = now
        transaction = Transaction(account_id=account.id, reference=f"transfer-{uuid.uuid4().hex}",
                                  direction="expense", amount_fen=transfer.amount_fen,
                                  balance_after_fen=account.balance_fen, counterparty=transfer.recipient_name,
                                  category="模拟转账", note=transfer.note, occurred_at=now)
        session.add(account)
        session.add(transaction)
        session.flush()
        transfer.status = "completed"
        transfer.transaction_id = transaction.id
        transfer.completed_at = now
        session.add(transfer)
        record(session, user_id=user_id, event_type="transfer_completed", transfer_id=transfer.id,
               transaction_id=transaction.id, tool="transfer", risk_level=decision.level.value, result="success")
        session.commit()
        return {"transfer_id": transfer.id, "transaction_id": transaction.id,
                "balance_fen": transaction.balance_after_fen}


def _record_failure(user_id: int, event_type: str, exc: Exception, *, transfer_id: int | None = None) -> None:
    denied = isinstance(exc, TransferError)
    message = str(exc) if denied else ""
    code = {
        "账户余额不足": "insufficient_balance", "账户币种不支持或余额不足": "insufficient_balance",
        "风险已升级，请重新发起并完成模拟验证": "risk_upgrade",
        "转账未确认、未验证、已取消或已过期": "not_authorized",
        "转账未确认、已取消或已过期": "not_authorized",
        "红色转账尚未通过模拟验证": "not_authorized", "模拟验证无效或已过期": "not_authorized",
        "请求编号已用于其他转账": "duplicate_mismatch", "红色操作暂不支持真实验证": "verification_unavailable",
        "转账风险等级无效": "invalid_risk",
    }.get(message, "unavailable" if denied else "internal_error")
    decision = exc.decision if denied else None
    with Session(get_engine()) as session:
        if decision is not None:
            record(session, user_id=user_id, event_type="risk_assessed", transfer_id=transfer_id,
                   tool="transfer", risk_level=decision.level.value, reasons=decision.reasons, result="denied")
        record(session, user_id=user_id, event_type=event_type, transfer_id=transfer_id,
               tool="prepare_transfer" if event_type.startswith("transfer_prepare") else "transfer",
               result="denied" if denied else "failed", reason_code=code)
        session.commit()


def prepare_transfer(user_id: int, payload: PrepareTransferRequest) -> dict:
    try:
        return _prepare_transfer(user_id, payload)
    except Exception as exc:
        denied = isinstance(exc, TransferError)
        _record_failure(user_id, "transfer_prepare_denied" if denied else "transfer_prepare_failed", exc)
        raise


def execute_transfer(user_id: int, transfer_id: int) -> dict:
    try:
        return _execute_transfer(user_id, transfer_id)
    except Exception as exc:
        denied = isinstance(exc, TransferError)
        _record_failure(user_id, "transfer_denied" if denied else "transfer_failed", exc, transfer_id=transfer_id)
        raise
