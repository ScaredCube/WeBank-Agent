
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.session import session_scope
from app.schemas.actions import PendingActionResponse
from app.schemas.transfers import PrepareTransferRequest
from app.services.action_service import get_pending_action
from app.services.transfer_service import TransferError, prepare_transfer
from app.services.operation_service import agent_preparation_key


class TransferArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_token: str | None = Field(
        default=None, description="付款账户由服务端绑定本轮用户明确选择的账户；未选择时不猜测账户或令牌。"
    )
    recipient_name: str = Field(
        min_length=1, max_length=80,
        description="只填收款人的姓名或称呼，如「模拟收款人」；绝不能附加手机号、银行卡号或其他数字联系方式。手机号只能用 target_token 传递。",
    )
    target_token: str | None = Field(
        default=None,
        description="用户输入手机号时，填写服务端在本轮上下文提供的 PHONE_TMP 临时引用；绝不填写明文手机号、猜测号码或拼接到收款人姓名。",
    )
    recipient_contact_token: str | None = None
    amount_fen: int = Field(gt=0, le=100_000_000_000, description="模拟转账金额，单位为分")
    note: str = Field(default="", max_length=120)


async def prepare_transfer_tool(*, user_id: int, **arguments: object) -> dict:
    """Prepare only; the caller must deliver the token to the user, never the model."""
    try:
        args = TransferArguments.model_validate(arguments)
        payload = PrepareTransferRequest.model_validate({
            "account_id": 1, "recipient_name": args.recipient_name,
            "amount_fen": args.amount_fen, "note": args.note,
            "idempotency_key": agent_preparation_key("transfer"),
        })
        result = prepare_transfer(user_id, payload, source_token=args.source_token,
                                  target_token=args.target_token,
                                  recipient_contact_token=args.recipient_contact_token, model_request=True)
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
