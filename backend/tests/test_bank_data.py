import re

from sqlmodel import Session, select

from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import Account, Card, Contact, User, WealthHolding


def _other_headers(session: Session) -> dict:
    other = User(username="bank_data_other", password_hash="test", display_name="其他")
    session.add(other)
    session.commit()
    session.refresh(other)
    return {"Authorization": f"Bearer {create_access_token(str(other.id))}"}


def test_bank_dashboard_shape_and_user_isolation(client, auth_headers):
    response = client.get("/api/bank/dashboard", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["balance_fen"] == 500_000
    assert data["accounts"][0]["can_transfer"] is True
    assert data["accounts"][0]["card_status"] == "active"
    assert len(data["contacts"]) == 2
    assert data["contacts"][0]["masked_phone"] == "138****0001"
    assert data["contacts"][0]["can_transfer"] is True
    assert len(data["holdings"]) == 1
    assert data["holdings"][0]["amount_fen"] == 100_000
    assert data["risk_profile"]["risk_level"] == "R2"
    assert response.headers["cache-control"] == "no-store"

    text = response.text
    assert "account_token" not in text and "product_token" not in text
    assert "confirmation_token" not in text
    assert not re.search(r"1[3-9]\d{9}", text)
    assert client.get("/api/bank/dashboard").status_code == 401

    with Session(get_engine()) as session:
        other_headers = _other_headers(session)
    other = client.get("/api/bank/dashboard", headers=other_headers)
    assert other.status_code == 200
    assert other.json()["accounts"] == []
    assert other.json()["contacts"] == []
    assert other.json()["holdings"] == []
    assert other.json()["risk_profile"]["risk_level"] == "未评估"


def test_bank_accounts_supports_multiple_accounts(client, auth_headers):
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
        second = Account(user_id=user_id, name="演示储蓄账户", masked_number="**** 0002",
                         balance_fen=12_345)
        session.add(second)
        session.commit()
        session.refresh(second)
        second_id = second.id

    accounts = client.get("/api/bank/accounts", headers=auth_headers)
    assert accounts.status_code == 200
    assert len(accounts.json()) == 2
    item = next(account for account in accounts.json() if account["account_id"] == second_id)
    assert item["balance_fen"] == 12_345
    assert item["card_status"] == "missing"
    assert item["can_transfer"] is False

    with Session(get_engine()) as session:
        session.add(Card(account_id=second_id))
        session.commit()
    item = next(account for account in client.get("/api/bank/accounts",
                                                  headers=auth_headers).json()
                if account["account_id"] == second_id)
    assert item["card_status"] == "active" and item["can_transfer"] is True


def test_bank_contacts_are_read_only_and_isolated(client, auth_headers):
    contacts = client.get("/api/bank/contacts", headers=auth_headers)
    assert contacts.status_code == 200
    assert len(contacts.json()) == 2
    assert all(contact["masked_phone"].count("*") >= 4 for contact in contacts.json())
    assert "王五" not in contacts.text
    assert client.post("/api/bank/contacts", headers=auth_headers,
                       json={"name": "王五"}).status_code == 405
    assert client.delete("/api/bank/contacts/1", headers=auth_headers).status_code in (404, 405)

    with Session(get_engine()) as session:
        other_headers = _other_headers(session)
    assert client.get("/api/bank/contacts", headers=other_headers).json() == []


def test_bank_dashboard_matches_database(client, auth_headers):
    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        account.balance_fen = 500_001
        holding = session.exec(select(WealthHolding).where(
            WealthHolding.product_id == 1)).one()
        holding.amount_fen = 123_456
        holding.yesterday_earnings_fen = 99
        contact = session.exec(select(Contact)).first()
        contact.status = "inactive"
        session.add(account)
        session.add(holding)
        session.add(contact)
        session.commit()

    data = client.get("/api/bank/dashboard", headers=auth_headers).json()
    assert data["accounts"][0]["balance_fen"] == 500_001
    assert data["holdings"][0]["amount_fen"] == 123_456
    assert data["holdings"][0]["yesterday_earnings_fen"] == 99
    inactive = next(item for item in data["contacts"] if item["status"] == "inactive")
    assert inactive["can_transfer"] is False


def test_bank_data_is_not_registered_as_agent_tools():
    from app.tools.register import create_agent_registry
    names = {item["function"]["name"] for item in create_agent_registry().definitions()}
    assert not {"read_accounts", "read_contacts", "read_dashboard"} & names
    assert "get_account_balance" in names
