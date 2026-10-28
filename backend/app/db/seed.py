from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import hash_password
from app.models import Account, Card, Transaction, User


def seed_demo_user(session: Session) -> User:
    user = session.exec(select(User).where(User.username == settings.demo_username)).first()
    if user:
        return user

    user = User(
        username=settings.demo_username,
        password_hash=hash_password(settings.demo_password),
        display_name=settings.demo_display_name,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def seed_demo_accounts(session: Session, user: User) -> None:
    """Create a single fictional account only when the demo user has none."""
    if user.id is None:
        raise ValueError("演示用户尚未保存")
    existing = session.exec(select(Account).where(Account.user_id == user.id)).first()
    if existing is not None:
        return

    account = Account(
        user_id=user.id, name="演示活期账户", masked_number="**** 0001",
        balance_fen=500000,
    )
    session.add(account)
    session.flush()
    entries = [
        ("income", 600000, 600000, "演示公司", "工资", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("expense", 50000, 550000, "演示餐厅", "餐饮", datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ("expense", 50000, 500000, "演示商店", "购物", datetime(2026, 1, 3, tzinfo=timezone.utc)),
    ]
    for index, (direction, amount, balance, counterparty, category, occurred_at) in enumerate(entries, 1):
        session.add(Transaction(
            account_id=account.id, reference=f"demo-{user.id}-{index}", direction=direction,
            amount_fen=amount, balance_after_fen=balance, counterparty=counterparty,
            category=category, note="模拟交易", occurred_at=occurred_at,
        ))
    session.commit()


def seed_demo_cards(session: Session, user: User) -> None:
    """Add one simulated card for each existing demo account without changing it."""
    accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
    for account in accounts:
        if session.exec(select(Card).where(Card.account_id == account.id)).first() is None:
            session.add(Card(account_id=account.id))
    session.commit()
