import secrets

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.session import session_scope
from app.schemas.actions import PendingActionResponse
from app.schemas.transfers import PrepareTransferRequest
from app.services.account_service import list_accounts
from app.services.action_service import get_pending_action
from app.services.transfer_service import TransferError, prepare_transfer


class TransferArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: int | None = Field(default=None, gt=0)
    recipient_name: str = Field(min_length=1, max_length=80)
    recipient_phone: str | None = Field(default=None, pattern=r"^1[0-9]{10}$")
    amount_fen: int = Field(gt=0, le=100_000_000_000, description="模拟转账金额，单位为分")
    note: str = Field(default="", max_length=120)


async def prepare_transfer_tool(*, user_id: int, **arguments: object) -> dict:
    """Prepare only; the caller must deliver the token to the user, never the model."""
    try:
        args = TransferArguments.model_validate(arguments)
        account_id = args.account_id
        if account_id is None:
            with session_scope() as session:
                accounts = list_accounts(session, user_id)
                if len(accounts) != 1:
                    return {"ok": False, "error": "请先指定付款账户"}
                account_id = accounts[0].id
        payload = PrepareTransferRequest.model_validate({
            **args.model_dump(), "account_id": account_id,
            "idempotency_key": secrets.token_urlsafe(24),
        })
        result = prepare_transfer(user_id, payload)
        with session_scope() as session:
            action = get_pending_action(session, user_id=user_id, action_id=result["action_id"])
        if action is None or result["confirmation_token"] is None:
            return {"ok": False, "error": "待确认动作不可用"}
        return {"ok": True, "transfer_id": result["transfer_id"],
                "confirmation_token": result["confirmation_token"],
                "action": PendingActionResponse.model_validate(action).model_dump(mode="json")}
    except ValidationError:
        return {"ok": False, "error": "转账参数无效"}
    except TransferError as exc:
        return {"ok": False, "error": str(exc)}
