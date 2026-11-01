"""Simulated collection request from a contact to one of the user's accounts."""
import uuid

from sqlmodel import Session, select

from app.agent.registry import RiskLevel, ToolSpec
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    Account, CollectionRequest, Contact, DataToken, PendingAction,
)
from app.risk.engine import assess_tool
from app.services.action_service import (
    create_pending_action, create_simulated_red_action, get_pending_action,
)
from app.services.audit_service import record, request_context
from app.services.operation_service import begin_write
from app.services.redaction import mask_text
from app.services.vault import resolve

_COLLECT_SPEC = ToolSpec(name="collection_request", description="模拟发起收款请求",
                         parameters={}, risk=RiskLevel.YELLOW)


class CollectionError(ValueError):
    pass


def prepare_collection(user_id: int, *, contact_token: str, account_token: str,
                       amount_fen: int, note: str = "", idempotency_key: str) -> dict:
    if type(amount_fen) is not int or amount_fen <= 0:
        raise CollectionError("收款金额无效")
    with Session(get_engine()) as session:
        begin_write(session, CollectionError, "收款请求不可用")
        scope = request_context.get() or uuid.uuid4().hex
        contact_id = resolve(session, user_id, contact_token, "contact", scope)
        account_id = resolve(session, user_id, account_token, "account", scope)
        contact = session.exec(select(Contact).where(
            Contact.id == contact_id, Contact.user_id == user_id, Contact.status == "active",
        )).first()
        account = session.exec(select(Account).where(
            Account.id == account_id, Account.user_id == user_id,
            Account.status == "active", Account.currency == "CNY",
        )).first()
        if contact is None:
            raise CollectionError("联系人不可用")
        if account is None:
            raise CollectionError("收款账户不可用")

        existing = session.exec(select(CollectionRequest).where(
            CollectionRequest.user_id == user_id,
            CollectionRequest.idempotency_key == idempotency_key,
        )).first()
        if existing is not None:
            if (existing.contact_id != contact.id or existing.account_id != account.id
                    or existing.amount_fen != amount_fen or existing.note != mask_text(note)):
                raise CollectionError("请求编号已用于其他收款")
            action = get_pending_action(session, user_id=user_id, action_id=existing.action_id)
            if action is None:
                raise CollectionError("待确认动作不可用")
            session.commit()
            return {"collection_id": existing.id, "confirmation_token": None, "action": action}

        contact_row = session.exec(select(DataToken).where(
            DataToken.token == contact_token, DataToken.user_id == user_id)).one()
        account_row = session.exec(select(DataToken).where(
            DataToken.token == account_token, DataToken.user_id == user_id)).one()
        details = {
            "contact_id": contact.id, "contact_name": mask_text(contact.name),
            "account_id": account.id, "account_masked": mask_text(account.masked_number),
            "amount_fen": amount_fen, "note": mask_text(note), "currency": "CNY",
        }
        decision = assess_tool(_COLLECT_SPEC)
        create_action = (create_simulated_red_action
                         if decision.level == RiskLevel.RED else create_pending_action)
        action, token = create_action(
            session, user_id=user_id, action_type="collection_request",
            details=details, decision=decision, commit=False,
        )
        request = CollectionRequest(
            user_id=user_id, contact_id=contact.id, account_id=account.id, action_id=action.id,
            idempotency_key=idempotency_key, amount_fen=amount_fen, note=mask_text(note),
            contact_token_id=contact_row.id, account_token_id=account_row.id, request_scope=scope,
        )
        session.add(request)
        session.flush()
        record(session, user_id=user_id, action_id=action.id,
               event_type="collection_prepared", tool="collection_request",
               risk_level=decision.level.value, result="success")
        session.commit()
        return {"collection_id": request.id, "confirmation_token": token,
                "action": get_pending_action(session, user_id=user_id, action_id=action.id)}


def execute_collection(user_id: int, collection_id: int) -> dict:
    with Session(get_engine()) as session:
        begin_write(session, CollectionError, "收款请求不可用")
        request = session.exec(select(CollectionRequest).where(
            CollectionRequest.id == collection_id, CollectionRequest.user_id == user_id,
        )).first()
        if request is None:
            raise CollectionError("收款请求不存在")
        if request.status == "completed":
            return {"collection_id": request.id, "status": "completed"}
        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == request.action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == "collection_request",
            PendingAction.risk_level.in_(("yellow", "red")),
            PendingAction.status.in_(("confirmed", "verified")),
            PendingAction.expires_at > now,
        )).first()
        if action is None:
            raise CollectionError("收款请求尚未确认/验证或已过期")
        request.status = "completed"
        request.completed_at = now
        action.status = "completed"
        session.add(request)
        session.add(action)
        record(session, user_id=user_id, action_id=action.id,
               event_type="collection_completed", tool="collection_request",
               risk_level="yellow", result="success")
        session.commit()
        return {"collection_id": request.id, "status": "completed"}
