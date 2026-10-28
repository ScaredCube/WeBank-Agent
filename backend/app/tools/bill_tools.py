from pydantic import BaseModel, ConfigDict, ValidationError
from sqlmodel import Session

from app.services.audit_service import request_context
from app.services.bill_service import BillError, monthly_bill
from app.services.vault import VaultError, resolve


class MonthlyBillArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    month: str | None = None
    account_token: str | None = None


async def get_monthly_bill(session: Session, user_id: int, **arguments: object) -> dict:
    try:
        args = MonthlyBillArguments.model_validate(arguments)
        account_id = resolve(session, user_id, args.account_token, "account", request_context.get() or "") if args.account_token else None
        bill = monthly_bill(session, user_id, args.month, account_id)
        return {"ok": True, "data": bill.model_dump(), "error": None}
    except ValidationError:
        return {"ok": False, "data": None, "error": "查询参数无效"}
    except VaultError:
        return {"ok": False, "data": None, "error": "引用不可用"}
    except BillError as exc:
        return {"ok": False, "data": None, "error": str(exc)}
