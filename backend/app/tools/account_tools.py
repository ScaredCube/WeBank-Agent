import logging
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session

from app.services.account_service import get_account, list_accounts, recent_transactions

logger = logging.getLogger(__name__)


class BalanceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: int | None = Field(default=None, gt=0)


class TransactionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=10, ge=1, le=50)


def _result(user_id: int, tool: str, data: object = None, error: str | None = None) -> dict:
    # Audit placeholder: no account details, tool arguments or credentials are logged.
    logger.info("tool=%s user_id=%s risk=green success=%s time=%s",
                tool, user_id, error is None, datetime.now(timezone.utc).isoformat())
    return {"ok": error is None, "data": data, "error": error}


async def get_account_balance(session: Session, user_id: int, **arguments: object) -> dict:
    tool = "get_account_balance"
    try:
        args = BalanceArguments.model_validate(arguments)
    except ValidationError:
        return _result(user_id, tool, error="查询参数无效")
    accounts = ([get_account(session, user_id, args.account_id)] if args.account_id
                else list_accounts(session, user_id))
    if args.account_id and accounts[0] is None:
        return _result(user_id, tool, error="账户不存在")
    return _result(user_id, tool, data=[
        {"account_id": account.id, "name": account.name, "masked_number": account.masked_number,
         "currency": account.currency, "balance_fen": account.balance_fen, "status": account.status}
        for account in accounts if account is not None
    ])


async def list_recent_transactions(session: Session, user_id: int, **arguments: object) -> dict:
    tool = "list_recent_transactions"
    try:
        args = TransactionArguments.model_validate(arguments)
    except ValidationError:
        return _result(user_id, tool, error="查询参数无效")
    account_id = args.account_id
    if account_id is None:
        accounts = list_accounts(session, user_id)
        if not accounts:
            return _result(user_id, tool, error="账户不存在")
        if len(accounts) != 1:
            return _result(user_id, tool, error="请指定要查询的账户")
        account_id = accounts[0].id
    transactions = recent_transactions(session, user_id, account_id, args.limit)
    if transactions is None:
        return _result(user_id, tool, error="账户不存在")
    return _result(user_id, tool, data=[
        {"reference": entry.reference, "direction": entry.direction, "amount_fen": entry.amount_fen,
         "balance_after_fen": entry.balance_after_fen, "counterparty": entry.counterparty,
         "category": entry.category, "note": entry.note, "occurred_at": entry.occurred_at.isoformat()}
        for entry in transactions
    ])
