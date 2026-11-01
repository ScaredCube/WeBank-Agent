"""Simulated card status and red-verified loss reporting."""
import uuid
from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, Card, CardLossRequest, PendingAction, VerificationSession
from app.risk.engine import RiskDecision
from app.services.action_service import create_simulated_red_action
from app.services.audit_service import record, record_separately, request_context
from app.services.operation_service import (begin_write, bind_preparation, check_prepared_reference,
                                            find_preparation)
from app.services.redaction import mask_text
from app.services.vault import VaultError, create_account_token, resolve


class CardError(Exception):
    pass


def list_cards(session: Session, user_id: int, account_token: str | None = None,
               card_id: int | None = None) -> list[dict]:
    account_id = resolve(session, user_id, account_token, "account", request_context.get() or "") if account_token else None
    query = select(Card, Account).join(Account, Card.account_id == Account.id).where(Account.user_id == user_id)
    if account_id is not None:
        query = query.where(Account.id == account_id)
    if card_id is not None:
        query = query.where(Card.id == card_id)
    rows = session.exec(query).all()
    result = []
    for card, account in rows:
        reference = create_account_token(session, user_id, account.id) if account.status == "active" else None
        result.append({"card_id": card.id, "account_id": account.id, "account_token": reference, "account_name": mask_text(account.name),
                       "masked_number": mask_text(account.masked_number), "status": card.status,
                       "account_status": account.status})
    return result


def _begin(session: Session) -> None:
    if not settings.debug:
        raise CardError("模拟挂失验证不可用")
    begin_write(session, CardError, "模拟挂失验证不可用")


def _owned_card(session: Session, user_id: int, card_id: int | None, account_token: str | None) -> tuple[Card, Account]:
    query = select(Card, Account).join(Account, Card.account_id == Account.id).where(Account.user_id == user_id)
    if card_id is not None:
        query = query.where(Card.id == card_id)
    if account_token is not None:
        account_id = resolve(session, user_id, account_token, "account", request_context.get() or "")
        query = query.where(Account.id == account_id)
    rows = session.exec(query).all()
    if len(rows) != 1:
        raise CardError("卡片不可用或请指定卡片")
    card, account = rows[0]
    if account.status != "active" or card.status != "active":
        raise CardError("卡片已挂失或不可用")
    return card, account


def prepare_loss(user_id: int, card_id: int | None = None, account_token: str | None = None,
                 *, idempotency_key: str | None = None) -> dict:
    try:
        with Session(get_engine()) as session:
            _begin(session)
            scope = request_context.get() or uuid.uuid4().hex
            # REST retries can retrieve a completed receipt even after the card
            # became unavailable. This returns no new authorization secret.
            if card_id is not None:
                existing = find_preparation(session, user_id, "card_loss", idempotency_key,
                                             card_id, CardError)
                if existing is not None:
                    session.commit()
                    return existing
            card, account = _owned_card(session, user_id, card_id, account_token)
            existing = find_preparation(session, user_id, "card_loss", idempotency_key,
                                         card.id, CardError)
            if existing is not None:
                session.commit()
                return existing
            account_token = account_token or create_account_token(session, user_id, account.id)
            decision = RiskDecision(RiskLevel.RED, ("工具基础风险等级",))
            action, token = create_simulated_red_action(session, user_id=user_id, action_type="card_loss",
                details={"card_id": card.id, "account_name": mask_text(account.name),
                         "masked_number": mask_text(account.masked_number)}, decision=decision, commit=False)
            session.add(CardLossRequest(user_id=user_id, card_id=card.id, action_id=action.id))
            bind_preparation(session, user_id, "card_loss", idempotency_key, card.id,
                             action.id, account_token, scope)
            record(session, user_id=user_id, action_id=action.id, event_type="risk_assessed", tool="card_loss",
                   risk_level="red", reasons=decision.reasons, result="success")
            record(session, user_id=user_id, action_id=action.id, event_type="card_loss_prepared",
                   tool="prepare_card_loss", risk_level="red", result="success")
            session.commit()
            return {"action_id": action.id, "confirmation_token": token}
    except (CardError, VaultError) as exc:
        record_separately(user_id=user_id, event_type="card_loss_denied", tool="prepare_card_loss", result="denied")
        raise CardError("卡片不可用或模拟验证未启用") from exc
    except Exception:
        record_separately(user_id=user_id, event_type="card_loss_failed", tool="prepare_card_loss", result="failed")
        raise


def execute_loss(user_id: int, action_id: int) -> dict:
    try:
        with Session(get_engine()) as session:
            _begin(session)
            request = session.exec(select(CardLossRequest).where(CardLossRequest.action_id == action_id,
                                   CardLossRequest.user_id == user_id)).first()
            if request is None:
                raise CardError("挂失动作不可用")
            card = session.get(Card, request.card_id)
            account = session.get(Account, card.account_id) if card else None
            if not account or account.user_id != user_id:
                raise CardError("卡片不可用")
            if request.status == "completed":
                record(session, user_id=user_id, action_id=action_id, event_type="card_loss_completed",
                       tool="card_loss", risk_level="red", result="retry")
                session.commit()
                return {"card_id": card.id, "status": "lost"}
            now = utcnow()
            action = session.exec(select(PendingAction).where(PendingAction.id == action_id,
                PendingAction.user_id == user_id, PendingAction.action_type == "card_loss",
                PendingAction.risk_level == "red", PendingAction.status == "verified", PendingAction.expires_at > now)).first()
            verification = session.exec(select(VerificationSession).where(VerificationSession.action_id == action_id,
                VerificationSession.user_id == user_id, VerificationSession.status == "verified",
                VerificationSession.expires_at > now)).first()
            if not action or not verification:
                raise CardError("挂失尚未通过有效的模拟验证")
            if account.status != "active" or card.status != "active":
                raise CardError("卡片已挂失或不可用")
            check_prepared_reference(session, user_id, "card_loss", action_id, card.id,
                                     "account", account.id)
            card.status = "lost"
            card.updated_at = now
            request.status = "completed"
            action.status = "completed"
            session.add(card); session.add(request); session.add(action)
            record(session, user_id=user_id, action_id=action_id, event_type="card_loss_completed",
                   tool="card_loss", risk_level="red", result="success")
            session.commit()
            return {"card_id": card.id, "status": "lost"}
    except VaultError:
        record_separately(user_id=user_id, action_id=action_id, event_type="token_resolve_denied",
                          result="denied", reason_code="reference_unavailable")
        record_separately(user_id=user_id, action_id=action_id, event_type="card_loss_denied",
                          tool="card_loss", result="denied", reason_code="reference_unavailable")
        raise CardError("引用不可用，请重新发起挂失") from None
    except CardError:
        record_separately(user_id=user_id, action_id=action_id, event_type="card_loss_denied",
                          tool="card_loss", result="denied")
        raise
    except Exception:
        record_separately(user_id=user_id, action_id=action_id, event_type="card_loss_failed",
                          tool="card_loss", result="failed")
        raise
