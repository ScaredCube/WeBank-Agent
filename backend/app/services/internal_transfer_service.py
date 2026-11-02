"""Server-owned internal transfer between two accounts of the same user."""
from datetime import datetime, timedelta, timezone
import uuid

from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    Account, Card, DataToken, InternalTransfer, PendingAction, Transaction,
)
from app.risk.engine import assess_internal_transfer
from app.services.action_service import (
    create_pending_action, create_simulated_red_action, get_pending_action,
)
from app.services.audit_service import record, request_context
from app.services.operation_service import begin_write
from app.services.redaction import mask_text
from app.services.vault import resolve

_LOCAL = timezone(timedelta(hours=8))


class InternalTransferError(ValueError):
    pass


def _account(session: Session, user_id: int, account_id: int) -> Account:
    account = session.exec(select(Account).where(
        Account.id == account_id, Account.user_id == user_id,
        Account.status == "active", Account.currency == "CNY",
    )).first()
    if account is None:
        raise InternalTransferError("账户不可用")
    card = session.exec(select(Card).where(Card.account_id == account.id)).first()
    if card is None or card.status != "active":
        raise InternalTransferError("账户银行卡不可用")
    return account


def _daily_total(session: Session, user_id: int, now: datetime) -> int:
    local_now = now.astimezone(_LOCAL)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    rows = session.exec(select(InternalTransfer).where(
        InternalTransfer.user_id == user_id,
        InternalTransfer.status == "completed",
        InternalTransfer.completed_at >= start,
    )).all()
    return sum(row.amount_fen for row in rows)


def _execute(session: Session, transfer: InternalTransfer, now: datetime) -> dict:
    source = _account(session, transfer.user_id, transfer.source_account_id)
    target = _account(session, transfer.user_id, transfer.target_account_id)
    if source.id == target.id:
        raise InternalTransferError("不能向同一账户转账")
    if source.balance_fen < transfer.amount_fen:
        raise InternalTransferError("账户余额不足")

    source.balance_fen -= transfer.amount_fen
    target.balance_fen += transfer.amount_fen
    source.updated_at = target.updated_at = now
    debit = Transaction(
        account_id=source.id, reference=f"internal-{uuid.uuid4().hex}", direction="expense",
        amount_fen=transfer.amount_fen, balance_after_fen=source.balance_fen,
        counterparty=mask_text(target.name), category="内部转账", note=transfer.note,
        occurred_at=now,
    )
    credit = Transaction(
        account_id=target.id, reference=f"internal-{uuid.uuid4().hex}", direction="income",
        amount_fen=transfer.amount_fen, balance_after_fen=target.balance_fen,
        counterparty=mask_text(source.name), category="内部转账", note=transfer.note,
        occurred_at=now,
    )
    session.add(source)
    session.add(target)
    session.add(debit)
    session.add(credit)
    session.flush()

    transfer.status = "completed"
    transfer.transaction_id = debit.id
    transfer.completed_at = now
    session.add(transfer)
    record(session, user_id=transfer.user_id, action_id=transfer.action_id,
           transaction_id=debit.id, event_type="internal_transfer_completed",
           tool="internal_transfer", risk_level="green", result="success")
    return {
        "transfer_id": transfer.id, "status": "completed",
        "amount_fen": transfer.amount_fen, "note": transfer.note,
        "source_name": mask_text(source.name), "source_masked": mask_text(source.masked_number),
        "target_name": mask_text(target.name), "target_masked": mask_text(target.masked_number),
        "balance_fen": source.balance_fen, "currency": "CNY",
        "transaction_id": debit.id,
    }


def prepare_internal_transfer(user_id: int, *, source_token: str, target_token: str,
                              amount_fen: int, note: str = "",
                              idempotency_key: str) -> dict:
    if type(amount_fen) is not int or amount_fen <= 0:
        raise InternalTransferError("转账金额无效")
    with Session(get_engine()) as session:
        begin_write(session, InternalTransferError, "内部转账不可用")
        scope = request_context.get() or uuid.uuid4().hex
        source_id = resolve(session, user_id, source_token, "account", scope)
        target_id = resolve(session, user_id, target_token, "account", scope)
        if not isinstance(source_id, int) or not isinstance(target_id, int) or source_id == target_id:
            raise InternalTransferError("收款账户无效")
        source = _account(session, user_id, source_id)
        target = _account(session, user_id, target_id)

        existing = session.exec(select(InternalTransfer).where(
            InternalTransfer.user_id == user_id,
            InternalTransfer.idempotency_key == idempotency_key,
        )).first()
        if existing is not None:
            if (existing.source_account_id != source.id or existing.target_account_id != target.id
                    or existing.amount_fen != amount_fen or existing.note != mask_text(note)):
                raise InternalTransferError("请求编号已用于其他转账")
            if existing.status == "completed":
                return {"ok": True, "executed": True,
                        "result": _result_from(existing, source, target)}
            action = (get_pending_action(session, user_id=user_id, action_id=existing.action_id)
                      if existing.action_id is not None else None)
            if action is None:
                raise InternalTransferError("待确认动作不可用")
            session.commit()
            return {"ok": True, "action": action, "confirmation_token": None,
                    "transfer_id": existing.id}

        now = utcnow()
        decision = assess_internal_transfer(amount_fen, _daily_total(session, user_id, now))
        source_row = session.exec(select(DataToken).where(
            DataToken.token == source_token, DataToken.user_id == user_id)).one()
        target_row = session.exec(select(DataToken).where(
            DataToken.token == target_token, DataToken.user_id == user_id)).one()
        transfer = InternalTransfer(
            user_id=user_id, source_account_id=source.id, target_account_id=target.id,
            action_id=None, idempotency_key=idempotency_key, amount_fen=amount_fen,
            note=mask_text(note), source_token_id=source_row.id, target_token_id=target_row.id,
            request_scope=scope,
        )
        if decision.level == RiskLevel.GREEN:
            session.add(transfer)
            session.flush()
            result = _execute(session, transfer, now)
            session.commit()
            return {"ok": True, "executed": True, "result": result}

        details = {
            "source_account_id": source.id, "source_masked": mask_text(source.masked_number),
            "source_name": mask_text(source.name),
            "target_account_id": target.id, "target_masked": mask_text(target.masked_number),
            "target_name": mask_text(target.name),
            "amount_fen": amount_fen, "note": mask_text(note), "currency": "CNY",
            "transfer_type": "internal",
        }
        create_action = (create_simulated_red_action
                         if decision.level == RiskLevel.RED else create_pending_action)
        action, token = create_action(
            session, user_id=user_id, action_type="internal_transfer",
            details=details, decision=decision, commit=False,
        )
        transfer.action_id = action.id
        session.add(transfer)
        session.flush()
        record(session, user_id=user_id, action_id=action.id,
               event_type="internal_transfer_prepared", tool="internal_transfer",
               risk_level=decision.level.value, result="success")
        session.commit()
        return {"ok": True, "transfer_id": transfer.id, "confirmation_token": token,
                "action": get_pending_action(session, user_id=user_id, action_id=action.id)}


def _result_from(transfer: InternalTransfer, source: Account, target: Account) -> dict:
    return {
        "transfer_id": transfer.id, "status": "completed", "amount_fen": transfer.amount_fen,
        "note": transfer.note, "source_name": mask_text(source.name),
        "source_masked": mask_text(source.masked_number), "target_name": mask_text(target.name),
        "target_masked": mask_text(target.masked_number), "balance_fen": source.balance_fen,
        "currency": "CNY", "transaction_id": transfer.transaction_id,
    }


def execute_internal_transfer(user_id: int, transfer_id: int) -> dict:
    with Session(get_engine()) as session:
        begin_write(session, InternalTransferError, "内部转账不可用")
        transfer = session.exec(select(InternalTransfer).where(
            InternalTransfer.id == transfer_id, InternalTransfer.user_id == user_id,
        )).first()
        if transfer is None:
            raise InternalTransferError("转账不存在")
        source = _account(session, user_id, transfer.source_account_id)
        target = _account(session, user_id, transfer.target_account_id)
        if transfer.status == "completed":
            return _result_from(transfer, source, target)
        if transfer.action_id is None:
            raise InternalTransferError("转账状态无效")
        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == transfer.action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == "internal_transfer",
            PendingAction.risk_level.in_(("yellow", "red")),
            PendingAction.status.in_(("confirmed", "verified")),
            PendingAction.expires_at > now,
        )).first()
        if action is None:
            raise InternalTransferError("转账尚未确认/验证或已过期")
        result = _execute(session, transfer, now)
        action.status = "completed"
        session.add(action)
        session.commit()
        return result
