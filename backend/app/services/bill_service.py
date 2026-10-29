"""Monthly statistics over the complete set of an owned account's transactions."""
import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.core.time import utcnow
from app.models import Account, Transaction, TransferRequest, WealthOrder
from app.schemas.bills import BillAnomaly, BillCategory, MonthlyBill
from app.services.redaction import mask_text

BEIJING = timezone(timedelta(hours=8))


class BillError(ValueError):
    pass


def month_bounds(month: str | None) -> tuple[str, datetime, datetime]:
    month = month if month is not None else utcnow().astimezone(BEIJING).strftime("%Y-%m")
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise BillError("月份无效，请使用 YYYY-MM")
    year, number = map(int, month.split("-"))
    # Both boundaries must be representable as datetimes.
    if year < 2 or year > 9998:
        raise BillError("月份无效，请使用 YYYY-MM")
    start = datetime(year, number, 1, tzinfo=BEIJING)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=BEIJING)
    return month, start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def monthly_bill(session: Session, user_id: int, month: str | None, account_id: int | None) -> MonthlyBill:
    month, start, end = month_bounds(month)
    query = select(Account).where(Account.user_id == user_id, Account.status == "active")
    if account_id is not None:
        query = query.where(Account.id == account_id)
    accounts = session.exec(query).all()
    if not accounts:
        raise BillError("账户不可用")
    if len(accounts) != 1:
        raise BillError("请指定要查询的账户")
    account = accounts[0]
    rows = session.exec(select(Transaction).where(
        Transaction.account_id == account.id, Transaction.occurred_at >= start,
        Transaction.occurred_at < end,
    ).order_by(col(Transaction.occurred_at), col(Transaction.id))).all()
    transfer_ids = set(session.exec(select(TransferRequest.transaction_id).where(
        TransferRequest.user_id == user_id, TransferRequest.account_id == account.id,
        TransferRequest.transaction_id.is_not(None),
    )).all())
    income = expense = consumption = count = out = out_count = incoming = incoming_count = ignored = 0
    investment_out = investment_out_count = investment_in = investment_in_count = 0
    investment_ids = set(session.exec(select(WealthOrder.transaction_id).where(
        WealthOrder.user_id == user_id, WealthOrder.account_id == account.id,
        WealthOrder.status == "completed", WealthOrder.transaction_id.is_not(None),
    )).all())
    categories: dict[str, list[int]] = {}
    previous: dict[tuple[str, int], datetime] = {}
    anomalies: list[BillAnomaly] = []
    for row in rows:
        is_transfer = row.id in transfer_ids or row.category == "模拟转账"
        is_investment = row.id in investment_ids or row.category in {"理财申购", "理财赎回"}
        if row.direction == "income":
            income += row.amount_fen
            if is_transfer:
                incoming += row.amount_fen
                incoming_count += 1
            elif is_investment:
                investment_in += row.amount_fen
                investment_in_count += 1
        elif row.direction == "expense":
            expense += row.amount_fen
            if is_transfer:
                out += row.amount_fen
                out_count += 1
                continue
            if is_investment:
                investment_out += row.amount_fen
                investment_out_count += 1
                continue
            consumption += row.amount_fen
            count += 1
            category = mask_text(row.category or "未分类")
            item = categories.setdefault(category, [0, 0])
            item[0] += row.amount_fen
            item[1] += 1
            when = row.occurred_at
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            key = (row.counterparty, row.amount_fen)
            earlier = previous.get(key)
            if row.counterparty.strip() and earlier is not None and timedelta(0) <= when - earlier <= timedelta(minutes=10):
                anomalies.append(BillAnomaly(reason="同一商户同金额消费在10分钟内重复", counterparty=mask_text(row.counterparty),
                    amount_fen=row.amount_fen, occurred_at=when.astimezone(BEIJING).isoformat(),
                    previous_occurred_at=earlier.astimezone(BEIJING).isoformat()))
            if row.counterparty.strip():
                previous[key] = when
        else:
            ignored += 1
    return MonthlyBill(month=month, account_name=mask_text(account.name), masked_number=mask_text(account.masked_number),
        currency=account.currency, income_fen=income, expense_fen=expense, consumption_fen=consumption,
        consumption_count=count, transfer_out_fen=out, transfer_out_count=out_count,
        transfer_in_fen=incoming, transfer_in_count=incoming_count,
        investment_out_fen=investment_out, investment_out_count=investment_out_count,
        investment_in_fen=investment_in, investment_in_count=investment_in_count,
        categories=[BillCategory(category=k, amount_fen=v[0], count=v[1]) for k, v in sorted(categories.items())],
        anomalies=anomalies, ignored_count=ignored)
