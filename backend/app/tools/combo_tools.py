from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.actions import PendingActionResponse
from app.services.collection_service import CollectionError, prepare_collection
from app.services.conversion_service import ConversionError, prepare_conversion
from app.services.internal_transfer_service import InternalTransferError, prepare_internal_transfer
from app.services.operation_service import agent_preparation_key


class InternalTransferArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_token: str = Field(min_length=1, max_length=128)
    target_token: str = Field(min_length=1, max_length=128)
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)


class CollectionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    contact_token: str = Field(min_length=1, max_length=128)
    account_token: str = Field(min_length=1, max_length=128)
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)


class ConversionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_token: str = Field(min_length=1, max_length=128)
    target_token: str = Field(min_length=1, max_length=128)
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)


def _json_action(result: dict) -> dict:
    """Service rows contain datetimes; SSE/model payloads must be JSON-safe."""
    action = result.get("action")
    if isinstance(action, dict):
        result["action"] = PendingActionResponse.model_validate(action).model_dump(mode="json")
    return result


async def prepare_internal_transfer_tool(*, user_id: int, **arguments: object) -> dict:
    try:
        args = InternalTransferArguments.model_validate(arguments)
        result = prepare_internal_transfer(
            user_id, source_token=args.source_token, target_token=args.target_token,
            amount_fen=args.amount_fen, note=args.note,
            idempotency_key=agent_preparation_key("internal_transfer"),
        )
        if result.get("executed"):
            result["result_kind"] = "internal_transfer"
        return _json_action(result)
    except ValidationError:
        return {"ok": False, "error": "内部转账参数无效"}
    except InternalTransferError as exc:
        return {"ok": False, "error": str(exc)}


async def prepare_collection_tool(*, user_id: int, **arguments: object) -> dict:
    try:
        args = CollectionArguments.model_validate(arguments)
        result = prepare_collection(
            user_id, contact_token=args.contact_token, account_token=args.account_token,
            amount_fen=args.amount_fen, note=args.note,
            idempotency_key=agent_preparation_key("collection_request"),
        )
        if result.get("action") is None:
            return {"ok": False, "error": "待确认动作不可用"}
        return _json_action({"ok": True, **result})
    except ValidationError:
        return {"ok": False, "error": "收款参数无效"}
    except CollectionError as exc:
        return {"ok": False, "error": str(exc)}


async def prepare_conversion_tool(*, user_id: int, **arguments: object) -> dict:
    try:
        args = ConversionArguments.model_validate(arguments)
        result = prepare_conversion(
            user_id, source_token=args.source_token, target_token=args.target_token,
            amount_fen=args.amount_fen, note=args.note,
            idempotency_key=agent_preparation_key("wealth_convert"),
        )
        if result.get("action") is None:
            return {"ok": False, "error": "待验证动作不可用"}
        return _json_action({"ok": True, **result})
    except ValidationError:
        return {"ok": False, "error": "转换参数无效"}
    except ConversionError as exc:
        return {"ok": False, "error": str(exc)}
