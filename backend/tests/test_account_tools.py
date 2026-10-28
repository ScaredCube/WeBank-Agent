import asyncio

from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.db.seed import seed_demo_accounts
from app.db.session import get_engine
from app.models import Account, Transaction, User
from app.tools.register import create_readonly_registry


def test_demo_seed_is_idempotent(client):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        seed_demo_accounts(session, user)
        seed_demo_accounts(session, user)
        accounts = session.exec(select(Account).where(Account.user_id == user.id)).all()
        assert len(accounts) == 1
        assert accounts[0].balance_fen == 500000
        assert len(session.exec(select(Transaction).where(Transaction.account_id == accounts[0].id)).all()) == 3


def test_readonly_tools_validate_and_isolate_accounts(client):
    registry = create_readonly_registry()
    balance = registry.get("get_account_balance")
    transactions = registry.get("list_recent_transactions")
    assert balance.risk == transactions.risk == RiskLevel.GREEN
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        other = User(username="other", password_hash="test", display_name="其他用户")
        session.add(other)
        session.commit()
        session.refresh(other)
        account = session.exec(select(Account).where(Account.user_id == user.id)).one()
        found = asyncio.run(balance.handler(session, user.id))
        assert found["ok"] and found["data"][0]["balance_fen"] == 500000
        account_token = found["data"][0]["account_token"]
        entries = asyncio.run(transactions.handler(session, user.id, account_token=account_token, limit=2))
        assert [entry["category"] for entry in entries["data"]] == ["购物", "餐饮"]
        default_entries = asyncio.run(transactions.handler(session, user.id))
        assert default_entries["ok"] and len(default_entries["data"]) == 3
        assert not asyncio.run(balance.handler(session, other.id, account_token=account_token))["ok"]
        assert not asyncio.run(transactions.handler(session, other.id, account_token=account_token))["ok"]
        assert not asyncio.run(transactions.handler(session, user.id, account_token=account_token, limit=51))["ok"]
        assert not asyncio.run(balance.handler(session, user.id, user_id_override=other.id))["ok"]
        session.refresh(account)
        assert account.balance_fen == 500000
