from pydantic import BaseModel, ConfigDict, ValidationError
from sqlmodel import Session

from app.db.session import session_scope
from app.schemas.actions import PendingActionResponse
from app.services.action_service import get_pending_action
from app.services.card_service import CardError, list_cards, prepare_loss
from app.services.vault import VaultError
from app.services.operation_service import agent_preparation_key


class CardArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_token: str | None = None


async def get_card_status(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        args = CardArguments.model_validate(arguments)
        return {"ok": True, "data": list_cards(session, user_id, args.account_token), "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}
    except VaultError:
        return {"ok": False, "data": None, "error": "引用不可用"}


async def prepare_card_loss(*, user_id: int, **arguments: object) -> dict:
    try:
        args = CardArguments.model_validate(arguments)
        result = prepare_loss(user_id, account_token=args.account_token,
                              idempotency_key=agent_preparation_key("card_loss"))
        with session_scope() as session:
            action = get_pending_action(session, user_id=user_id, action_id=result["action_id"])
        if action is None or result["confirmation_token"] is None:
            return {"ok": False, "error": "挂失动作不可用"}
        return {"ok": True, "action": PendingActionResponse.model_validate(action).model_dump(mode="json"),
                "confirmation_token": result["confirmation_token"]}
    except ValidationError:
        return {"ok": False, "error": "挂失参数无效"}
    except CardError as exc:
        return {"ok": False, "error": str(exc)}
