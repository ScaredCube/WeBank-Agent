from sqlmodel import Session, col, select

from app.models import Account, Transaction


def list_accounts(session: Session, user_id: int) -> list[Account]:
    return list(session.exec(
        select(Account).where(Account.user_id == user_id).order_by(col(Account.id))
    ).all())


def get_account(session: Session, user_id: int, account_id: int) -> Account | None:
    return session.exec(select(Account).where(
        Account.id == account_id, Account.user_id == user_id,
    )).first()


def recent_transactions(
    session: Session, user_id: int, account_id: int, limit: int = 10,
) -> list[Transaction] | None:
    if not 1 <= limit <= 50:
        raise ValueError("查询条数必须在 1 到 50 之间")
    if get_account(session, user_id, account_id) is None:
        return None
    return list(session.exec(
        select(Transaction).where(Transaction.account_id == account_id)
        .order_by(col(Transaction.occurred_at).desc(), col(Transaction.id).desc())
        .limit(limit)
    ).all())
