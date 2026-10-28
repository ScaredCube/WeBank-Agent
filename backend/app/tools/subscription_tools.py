from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session

from app.db.session import session_scope
from app.schemas.actions import PendingActionResponse
from app.services.action_service import get_pending_action
from app.services.subscription_service import (
    SubscriptionError, detect_candidates, list_subscriptions, prepare_cancel,
)
from app.services.vault import VaultError, create_subscription_token


class SubscriptionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SubscriptionCancelArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subscription_token: str = Field(min_length=1, max_length=128)


async def get_subscriptions(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        SubscriptionArguments.model_validate(arguments)
        data = list_subscriptions(session, user_id)
        for item in data:
            item["subscription_token"] = (
                create_subscription_token(session, user_id, item["subscription_id"])
                if item["can_cancel"] else None)
        return {"ok": True, "data": data, "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}
    except VaultError:
        return {"ok": False, "data": None, "error": "引用不可用"}


async def detect_subscriptions(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        SubscriptionArguments.model_validate(arguments)
        return {"ok": True, "data": detect_candidates(session, user_id), "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}


async def prepare_cancel_subscription(*, user_id: int, **arguments: object) -> dict:
    try:
        args = SubscriptionCancelArguments.model_validate(arguments)
        result = prepare_cancel(user_id, subscription_token=args.subscription_token,
                                model_request=True)
        with session_scope() as session:
            action = get_pending_action(session, user_id=user_id, action_id=result["action_id"])
        if action is None or result["confirmation_token"] is None:
            return {"ok": False, "error": "待确认动作不可用"}
        return {"ok": True, "subscription_id": result["subscription_id"],
                "confirmation_token": result["confirmation_token"],
                "action": PendingActionResponse.model_validate(action).model_dump(mode="json")}
    except ValidationError:
        return {"ok": False, "error": "取消订阅参数无效"}
    except SubscriptionError as exc:
        return {"ok": False, "error": str(exc)}
