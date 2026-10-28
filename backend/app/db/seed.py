from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    Account, Card, Contact, Subscription, Transaction, User, WealthHolding, WealthProduct,
    WealthRiskProfile,
)


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


DEMO_CONTACTS = (
    ("张三", "招商银行", "138****0001"),
    ("李四", "工商银行", "139****0002"),
)


def seed_demo_contacts(session: Session, user: User) -> None:
    """Read-only fictional contacts; no phone plaintext is stored or exposed."""
    for name, bank_name, masked_phone in DEMO_CONTACTS:
        existing = session.exec(select(Contact).where(
            Contact.user_id == user.id, Contact.name == name)).first()
        if existing is None:
            session.add(Contact(user_id=user.id, name=name, bank_name=bank_name,
                                masked_phone=masked_phone))
    session.commit()


DEMO_SUBSCRIPTIONS = (
    ("视频会员", 2_500, "monthly", 3),
    ("云存储", 1_200, "monthly", 20),
)


def seed_demo_subscriptions(session: Session, user: User) -> None:
    """Create fictional read-only subscriptions without changing balances."""
    today = utcnow().astimezone(timezone(timedelta(hours=8))).date()
    for merchant, amount_fen, cycle, days_ahead in DEMO_SUBSCRIPTIONS:
        existing = session.exec(select(Subscription).where(
            Subscription.user_id == user.id, Subscription.merchant == merchant)).first()
        if existing is None:
            session.add(Subscription(user_id=user.id, merchant=merchant, amount_fen=amount_fen,
                                     cycle=cycle, next_charge_date=today + timedelta(days=days_ahead)))
    session.commit()


DEMO_WEALTH_PRODUCTS = (
    ("稳稳盈 90 天", "稳健理财", "R1", 280, 90, 10_000),
    ("安心债券 A", "债券基金", "R2", 320, 0, 10_000),
    ("成长混合 C", "混合基金", "R3", 450, 0, 10_000),
)


def seed_demo_wealth(session: Session, user: User) -> None:
    """Create fictional products and one holding without touching account balances."""
    if user.id is None:
        raise ValueError("演示用户尚未保存")
    products: list[WealthProduct] = []
    for name, category, risk_level, rate_bps, term_days, min_amount_fen in DEMO_WEALTH_PRODUCTS:
        product = session.exec(select(WealthProduct).where(WealthProduct.name == name)).first()
        if product is None:
            product = WealthProduct(name=name, category=category, risk_level=risk_level,
                                    expected_rate_bps=rate_bps, term_days=term_days,
                                    min_amount_fen=min_amount_fen)
            session.add(product)
            session.flush()
        products.append(product)
    first = products[0]
    existing = session.exec(select(WealthHolding).where(
        WealthHolding.user_id == user.id, WealthHolding.product_id == first.id)).first()
    if existing is None:
        session.add(WealthHolding(user_id=user.id, product_id=first.id,
                                  amount_fen=100_000, yesterday_earnings_fen=80))
    if session.get(WealthRiskProfile, user.id) is None:
        session.add(WealthRiskProfile(user_id=user.id, risk_level="R2", score=4))
    session.commit()
