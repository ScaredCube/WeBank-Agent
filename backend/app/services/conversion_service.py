"""Simulated conversion between two of the user's wealth holdings."""
import uuid

from sqlmodel import Session, select

from app.agent.registry import RiskLevel, ToolSpec
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    DataToken, PendingAction, VerificationSession, WealthConversion, WealthHolding, WealthProduct,
)
from app.risk.engine import assess_tool
from app.services.action_service import create_simulated_red_action, get_pending_action
from app.services.audit_service import record, request_context
from app.services.operation_service import begin_write
from app.services.redaction import mask_text
from app.services.vault import resolve

_CONVERT_SPEC = ToolSpec(name="wealth_convert", description="模拟持仓转换",
                         parameters={}, risk=RiskLevel.RED)


class ConversionError(ValueError):
    pass


def _product(session: Session, product_id: int) -> WealthProduct:
    product = session.get(WealthProduct, product_id)
    if product is None or product.status != "available":
        raise ConversionError("理财产品不可用")
    return product


def _holding(session: Session, user_id: int, product_id: int) -> WealthHolding | None:
    return session.exec(select(WealthHolding).where(
        WealthHolding.user_id == user_id, WealthHolding.product_id == product_id,
    )).first()


def prepare_conversion(user_id: int, *, source_token: str, target_token: str,
                       amount_fen: int, note: str = "", idempotency_key: str) -> dict:
    if type(amount_fen) is not int or amount_fen <= 0:
        raise ConversionError("转换金额无效")
    with Session(get_engine()) as session:
        begin_write(session, ConversionError, "持仓转换不可用")
        scope = request_context.get() or uuid.uuid4().hex
        source_id = resolve(session, user_id, source_token, "product", scope)
        target_id = resolve(session, user_id, target_token, "product", scope)
        if source_id == target_id:
            raise ConversionError("不能转换到同一产品")
        source = _product(session, source_id)
        target = _product(session, target_id)
        holding = _holding(session, user_id, source.id)
        if holding is None or holding.amount_fen < amount_fen:
            raise ConversionError("持仓不足")

        existing = session.exec(select(WealthConversion).where(
            WealthConversion.user_id == user_id,
            WealthConversion.idempotency_key == idempotency_key,
        )).first()
        if existing is not None:
            if (existing.source_product_id != source.id or existing.target_product_id != target.id
                    or existing.amount_fen != amount_fen or existing.note != mask_text(note)):
                raise ConversionError("请求编号已用于其他转换")
            action = get_pending_action(session, user_id=user_id, action_id=existing.action_id)
            if action is None:
                raise ConversionError("待验证动作不可用")
            session.commit()
            return {"conversion_id": existing.id, "confirmation_token": None, "action": action}

        source_row = session.exec(select(DataToken).where(
            DataToken.token == source_token, DataToken.user_id == user_id)).one()
        target_row = session.exec(select(DataToken).where(
            DataToken.token == target_token, DataToken.user_id == user_id)).one()
        details = {
            "source_product_id": source.id, "source_product_name": mask_text(source.name),
            "target_product_id": target.id, "target_product_name": mask_text(target.name),
            "amount_fen": amount_fen, "note": mask_text(note), "currency": "CNY",
        }
        action, token = create_simulated_red_action(
            session, user_id=user_id, action_type="wealth_convert",
            details=details, decision=assess_tool(_CONVERT_SPEC), commit=False,
        )
        conversion = WealthConversion(
            user_id=user_id, source_product_id=source.id, target_product_id=target.id,
            action_id=action.id, idempotency_key=idempotency_key, amount_fen=amount_fen,
            note=mask_text(note), source_token_id=source_row.id, target_token_id=target_row.id,
            request_scope=scope,
        )
        session.add(conversion)
        session.flush()
        record(session, user_id=user_id, action_id=action.id,
               event_type="wealth_conversion_prepared", tool="wealth_convert",
               risk_level="red", result="success")
        session.commit()
        return {"conversion_id": conversion.id, "confirmation_token": token,
                "action": get_pending_action(session, user_id=user_id, action_id=action.id)}


def execute_conversion(user_id: int, conversion_id: int) -> dict:
    with Session(get_engine()) as session:
        begin_write(session, ConversionError, "持仓转换不可用")
        conversion = session.exec(select(WealthConversion).where(
            WealthConversion.id == conversion_id, WealthConversion.user_id == user_id,
        )).first()
        if conversion is None:
            raise ConversionError("转换不存在")
        if conversion.status == "completed":
            return {"conversion_id": conversion.id, "status": "completed",
                    "amount_fen": conversion.amount_fen}
        now = utcnow()
        action = session.exec(select(PendingAction).where(
            PendingAction.id == conversion.action_id, PendingAction.user_id == user_id,
            PendingAction.action_type == "wealth_convert",
            PendingAction.risk_level == "red", PendingAction.status == "verified",
            PendingAction.expires_at > now,
        )).first()
        verification = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == conversion.action_id,
            VerificationSession.user_id == user_id, VerificationSession.status == "verified",
            VerificationSession.expires_at > now,
        )).first()
        if action is None or verification is None:
            raise ConversionError("转换尚未通过有效模拟验证")

        source = _product(session, conversion.source_product_id)
        target = _product(session, conversion.target_product_id)
        source_holding = _holding(session, user_id, source.id)
        if source_holding is None or source_holding.amount_fen < conversion.amount_fen:
            raise ConversionError("持仓不足")
        target_holding = _holding(session, user_id, target.id)
        if target_holding is None:
            target_holding = WealthHolding(user_id=user_id, product_id=target.id, amount_fen=0)
            session.add(target_holding)
            session.flush()

        original = source_holding.amount_fen
        source_holding.amount_fen -= conversion.amount_fen
        if original > 0:
            source_holding.yesterday_earnings_fen = (
                source_holding.yesterday_earnings_fen * source_holding.amount_fen // original)
        source_holding.status = "active" if source_holding.amount_fen > 0 else "redeemed"
        source_holding.updated_at = now
        target_holding.amount_fen += conversion.amount_fen
        target_holding.status = "active"
        target_holding.updated_at = now
        conversion.status = "completed"
        conversion.completed_at = now
        action.status = "completed"
        session.add(source_holding)
        session.add(target_holding)
        session.add(conversion)
        session.add(action)
        record(session, user_id=user_id, action_id=action.id,
               event_type="wealth_conversion_completed", tool="wealth_convert",
               risk_level="red", result="success")
        session.commit()
        return {
            "conversion_id": conversion.id, "status": "completed",
            "amount_fen": conversion.amount_fen,
            "source_product_name": mask_text(source.name),
            "target_product_name": mask_text(target.name),
            "source_holding_fen": source_holding.amount_fen,
            "target_holding_fen": target_holding.amount_fen,
        }
