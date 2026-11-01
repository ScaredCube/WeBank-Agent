from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_engine
from app.models import Account, Card, Contact, WealthHolding, WealthProduct
from app.services.collection_service import execute_collection, prepare_collection
from app.services.conversion_service import execute_conversion, prepare_conversion
from app.services.internal_transfer_service import (
    execute_internal_transfer, prepare_internal_transfer,
)
from app.services.vault import create_account_token, create_contact_token, create_product_token


def _second_account(user_id: int) -> int:
    with Session(get_engine()) as session:
        account = Account(user_id=user_id, name="第二账户", masked_number="**** 0099",
                          balance_fen=200_000)
        session.add(account)
        session.flush()
        session.add(Card(account_id=account.id))
        session.commit()
        return account.id


def _tokens(account_id: int, user_id: int):
    with Session(get_engine()) as session:
        return create_account_token(session, user_id, account_id)


def test_internal_transfer_green_executes_and_yellow_requires_confirmation(client, auth_headers):
    with Session(get_engine()) as session:
        user_id = session.exec(select(Account)).first().user_id
        source = session.exec(select(Account)).first()
    target_id = _second_account(user_id)
    with Session(get_engine()) as session:
        source_token = create_account_token(session, user_id, source.id)
        target_token = create_account_token(session, user_id, target_id)
        session.commit()

    green = prepare_internal_transfer(
        user_id, source_token=source_token, target_token=target_token,
        amount_fen=50_000, note="内部", idempotency_key="green-internal-123456",
    )
    assert green["executed"] is True
    with Session(get_engine()) as session:
        assert session.get(Account, source.id).balance_fen == 450_000
        assert session.get(Account, target_id).balance_fen == 250_000

    yellow = prepare_internal_transfer(
        user_id, source_token=source_token, target_token=target_token,
        amount_fen=200_000, note="大额", idempotency_key="yellow-internal-123456",
    )
    assert not yellow.get("executed")
    action = yellow["action"]
    assert action["risk_level"] == "yellow"
    confirm = client.post(f"/api/actions/{action['id']}/confirm",
                          json={"token": yellow["confirmation_token"]}, headers=auth_headers)
    assert confirm.status_code == 200
    executed = client.post(f"/api/internal-transfers/{yellow['transfer_id']}/execute",
                           headers=auth_headers)
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"


def test_collection_is_yellow_and_does_not_move_money(client, auth_headers, monkeypatch):
    hour = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).first()
        contact = session.exec(select(Contact)).first()
        user_id = account.user_id
        contact_token = create_contact_token(session, user_id, contact.id)
        account_token = create_account_token(session, user_id, account.id)
        session.commit()
        before = account.balance_fen

    result = prepare_collection(
        user_id, contact_token=contact_token, account_token=account_token,
        amount_fen=12_300, note="AA", idempotency_key="collection-12345678",
    )
    action = result["action"]
    assert action["risk_level"] == "yellow"
    confirm = client.post(f"/api/actions/{action['id']}/confirm",
                          json={"token": result["confirmation_token"]}, headers=auth_headers)
    assert confirm.status_code == 200
    executed = client.post(f"/api/collections/{result['collection_id']}/execute",
                           headers=auth_headers)
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    with Session(get_engine()) as session:
        assert session.get(Account, account.id).balance_fen == before


def test_conversion_requires_red_verification(client, auth_headers):
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).first()
        user_id = account.user_id
        products = session.exec(select(WealthProduct).order_by(WealthProduct.id).limit(2)).all()
        first, second = products
        if session.exec(select(WealthHolding).where(
                WealthHolding.user_id == user_id, WealthHolding.product_id == second.id)).first() is None:
            session.add(WealthHolding(user_id=user_id, product_id=second.id, amount_fen=100_000))
            session.commit()
        source_token = create_product_token(session, user_id, first.id)
        target_token = create_product_token(session, user_id, second.id)
        session.commit()
        first_holding = session.exec(select(WealthHolding).where(
            WealthHolding.user_id == user_id, WealthHolding.product_id == first.id)).one()

    result = prepare_conversion(
        user_id, source_token=source_token, target_token=target_token,
        amount_fen=20_000, note="调仓", idempotency_key="conversion-12345678",
    )
    action = result["action"]
    assert action["risk_level"] == "red"
    start = client.post(f"/api/actions/{action['id']}/verification/start",
                        json={"token": result["confirmation_token"]}, headers=auth_headers)
    assert start.status_code == 200
    verify = client.post(f"/api/actions/{action['id']}/verification/verify",
                         json={"token": result["confirmation_token"], "code": "123456"},
                         headers=auth_headers)
    assert verify.status_code == 200 and verify.json()["status"] == "code_verified"
    face = client.post(f"/api/actions/{action['id']}/verification/face",
                       json={"token": result["confirmation_token"]}, headers=auth_headers)
    assert face.status_code == 200
    executed = client.post(f"/api/wealth/conversions/{result['conversion_id']}/execute",
                           headers=auth_headers)
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    with Session(get_engine()) as session:
        holding = session.get(WealthHolding, first_holding.id)
        assert holding.amount_fen == 80_000
