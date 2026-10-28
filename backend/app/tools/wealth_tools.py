import secrets

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session

from app.db.session import session_scope
from app.schemas.actions import PendingActionResponse
from app.schemas.wealth import PrepareWealthRedeemRequest, PrepareWealthSubscribeRequest
from app.services.action_service import get_pending_action
from app.services.audit_service import request_context
from app.services.vault import VaultError, create_product_token, resolve
from app.services.wealth_service import (
    WealthError, get_risk_profile, list_holdings, list_products, prepare_redeem, prepare_subscribe,
)


class WealthProductArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_token: str | None = None


class WealthHoldingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WealthRiskArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WealthPrepareArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_token: str = Field(min_length=1, max_length=128)
    account_token: str | None = None
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)


async def get_wealth_products(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        args = WealthProductArguments.model_validate(arguments)
        products = list_products(session, user_id)
        if args.product_token is not None:
            product_id = resolve(session, user_id, args.product_token, "product",
                                 request_context.get() or "")
            products = [product for product in products if product["product_id"] == product_id]
        data = [{**product, "product_token": create_product_token(
            session, user_id, product["product_id"])} for product in products]
        return {"ok": True, "data": data, "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}
    except VaultError:
        return {"ok": False, "data": None, "error": "引用不可用"}
    except WealthError as exc:
        return {"ok": False, "data": None, "error": str(exc)}


async def get_wealth_holdings(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        WealthHoldingArguments.model_validate(arguments)
        data = [{**holding, "product_token": create_product_token(
            session, user_id, holding["product_id"])} for holding in list_holdings(session, user_id)]
        return {"ok": True, "data": data, "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}
    except VaultError:
        return {"ok": False, "data": None, "error": "引用不可用"}
    except WealthError as exc:
        return {"ok": False, "data": None, "error": str(exc)}


async def get_wealth_risk_profile(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        WealthRiskArguments.model_validate(arguments)
        return {"ok": True, "data": get_risk_profile(session, user_id), "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}


def _prepare_payload(arguments: dict) -> dict:
    return {"product_id": 1, "account_id": None, "amount_fen": arguments["amount_fen"],
            "note": arguments.get("note", ""),
            "idempotency_key": secrets.token_urlsafe(24)}


async def _prepare_result(user_id: int, result: dict) -> dict:
    with session_scope() as session:
        action = get_pending_action(session, user_id=user_id, action_id=result["action_id"])
    if action is None or result["confirmation_token"] is None:
        return {"ok": False, "error": "待验证动作不可用"}
    return {"ok": True, "order_id": result["order_id"],
            "confirmation_token": result["confirmation_token"],
            "action": PendingActionResponse.model_validate(action).model_dump(mode="json")}


async def prepare_wealth_subscribe(*, user_id: int, **arguments: object) -> dict:
    try:
        args = WealthPrepareArguments.model_validate(arguments)
        payload = PrepareWealthSubscribeRequest.model_validate(_prepare_payload(args.model_dump()))
        result = prepare_subscribe(user_id, payload, product_token=args.product_token,
                                   account_token=args.account_token, model_request=True)
        return await _prepare_result(user_id, result)
    except ValidationError:
        return {"ok": False, "error": "理财申购参数无效"}
    except WealthError as exc:
        return {"ok": False, "error": str(exc)}


async def prepare_wealth_redeem(*, user_id: int, **arguments: object) -> dict:
    try:
        args = WealthPrepareArguments.model_validate(arguments)
        payload = PrepareWealthRedeemRequest.model_validate(_prepare_payload(args.model_dump()))
        result = prepare_redeem(user_id, payload, product_token=args.product_token,
                                account_token=args.account_token, model_request=True)
        return await _prepare_result(user_id, result)
    except ValidationError:
        return {"ok": False, "error": "理财赎回参数无效"}
    except WealthError as exc:
        return {"ok": False, "error": str(exc)}
