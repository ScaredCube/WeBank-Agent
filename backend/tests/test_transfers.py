from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, PendingAction, Transaction, TransferRequest, User, VerificationSession
from app.schemas.transfers import PrepareTransferRequest
from app.services.transfer_service import TransferError, execute_transfer, prepare_transfer


@pytest.fixture(autouse=True)
def daytime_policy(monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)


def payload(key="a" * 16, amount=50000):
    return {"account_id": 1, "recipient_name": "模拟收款人", "recipient_phone": "13812345678",
            "amount_fen": amount, "note": "测试", "idempotency_key": key}


def balance():
    with Session(get_engine()) as session:
        return session.get(Account, 1).balance_fen


def prepare(client, headers, data=None):
    return client.post("/api/transfers/prepare", json=data or payload(), headers=headers)


def confirm(client, headers, data):
    return client.post(f"/api/actions/{data['action_id']}/confirm",
                       json={"token": data["confirmation_token"]}, headers=headers)


def test_transfer_requires_confirmation_and_is_idempotent(client, auth_headers):
    response = prepare(client, auth_headers)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    result = response.json()
    assert balance() == 500000
    action = client.get(f"/api/actions/{result['action_id']}", headers=auth_headers).json()
    assert action["details"]["recipient_phone_masked"] == "138****5678"
    assert "13812345678" not in str(action)
    path = f"/api/transfers/{result['transfer_id']}/execute"
    assert client.post(path, headers=auth_headers).status_code == 400
    assert confirm(client, auth_headers, result).status_code == 200
    first = client.post(path, headers=auth_headers)
    assert first.status_code == 200 and first.json()["balance_fen"] == 450000
    assert client.post(path, headers=auth_headers).json() == first.json()
    assert balance() == 450000
    repeated = prepare(client, auth_headers).json()
    assert repeated["transfer_id"] == result["transfer_id"] and repeated["confirmation_token"] is None
    assert prepare(client, auth_headers, payload(amount=50001)).status_code == 400
    with Session(get_engine()) as session:
        entries = session.exec(select(Transaction).where(Transaction.category == "模拟转账")).all()
        assert len(entries) == 1 and entries[0].amount_fen == 50000


def test_insufficient_and_untrusted_fields_are_rejected(client, auth_headers):
    assert prepare(client, auth_headers, payload(amount=600000)).status_code == 400
    forged = payload()
    forged["daily_total_fen"] = 0
    assert prepare(client, auth_headers, forged).status_code == 422
    assert balance() == 500000


def test_red_transfer_requires_demo_verification_and_is_idempotent(client, auth_headers):
    response = prepare(client, auth_headers, payload(amount=100001))
    assert response.status_code == 200
    result = response.json()
    assert result["risk_level"] == "red" and "模拟验证码" in result["message"]
    action_path = f"/api/actions/{result['action_id']}"
    transfer_path = f"/api/transfers/{result['transfer_id']}/execute"
    assert client.get(action_path, headers=auth_headers).json()["risk_level"] == "red"
    assert confirm(client, auth_headers, result).status_code == 400
    assert client.post(transfer_path, headers=auth_headers).status_code == 400
    token = result["confirmation_token"]
    assert client.post(action_path + "/verification/start", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(action_path + "/verification/verify", json={"token": token, "code": "000000"},
                       headers=auth_headers).status_code == 400
    assert client.post(transfer_path, headers=auth_headers).status_code == 400
    assert balance() == 500000
    verified = client.post(action_path + "/verification/verify",
                           json={"token": token, "code": settings.demo_verification_code}, headers=auth_headers)
    assert verified.status_code == 200
    result1 = client.post(transfer_path, headers=auth_headers)
    assert result1.status_code == 200 and result1.json()["balance_fen"] == 399999
    assert client.post(transfer_path, headers=auth_headers).json() == result1.json()
    assert balance() == 399999


def test_red_transfer_disabled_without_debug_and_after_demo_disabled(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    assert prepare(client, auth_headers, payload(amount=100001)).status_code == 400
    monkeypatch.setattr(settings, "debug", True)
    result = prepare(client, auth_headers, payload(amount=100001)).json()
    path = f"/api/actions/{result['action_id']}/verification"
    token = result["confirmation_token"]
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 200
    monkeypatch.setattr(settings, "debug", False)
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_red_verification_expiry_prevents_execution(client, auth_headers):
    result = prepare(client, auth_headers, payload(amount=100001)).json()
    path = f"/api/actions/{result['action_id']}/verification"
    token = result["confirmation_token"]
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 200
    with Session(get_engine()) as session:
        verification = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == result["action_id"])).one()
        verification.expires_at = utcnow() - timedelta(seconds=1)
        session.add(verification)
        session.commit()
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_red_verification_lock_prevents_execution(client, auth_headers):
    result = prepare(client, auth_headers, payload(amount=100001)).json()
    path = f"/api/actions/{result['action_id']}/verification"
    token = result["confirmation_token"]
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    for _ in range(3):
        assert client.post(path + "/verify", json={"token": token, "code": "000000"},
                           headers=auth_headers).status_code == 400
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 400
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_night_upgrades_small_transfer_to_red(client, auth_headers, monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", hour)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 1) % 24)
    result = prepare(client, auth_headers).json()
    assert client.get(f"/api/actions/{result['action_id']}", headers=auth_headers).json()["risk_level"] == "red"
    assert confirm(client, auth_headers, result).status_code == 400
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_transfer_isolation_and_cancel(client, auth_headers):
    result = prepare(client, auth_headers).json()
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    assert prepare(client, other_headers, payload(key="b" * 16)).status_code == 400
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=other_headers).status_code == 400
    assert client.post(f"/api/actions/{result['action_id']}/cancel", headers=auth_headers).status_code == 200
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_second_transfer_rechecks_trusted_daily_total(client, auth_headers):
    first = prepare(client, auth_headers, payload(key="a" * 16, amount=60000)).json()
    second = prepare(client, auth_headers, payload(key="b" * 16, amount=40001)).json()
    assert confirm(client, auth_headers, first).status_code == 200
    assert confirm(client, auth_headers, second).status_code == 200
    assert client.post(f"/api/transfers/{first['transfer_id']}/execute", headers=auth_headers).status_code == 200
    assert client.post(f"/api/transfers/{second['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 440000


def test_concurrent_execute_debits_once(client, auth_headers):
    result = prepare(client, auth_headers).json()
    assert confirm(client, auth_headers, result).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: execute_transfer(user_id, result["transfer_id"]), range(2)))
    assert results[0]["transaction_id"] == results[1]["transaction_id"]
    assert balance() == 450000


def test_transaction_failure_rolls_back_balance_and_status(client, auth_headers, monkeypatch):
    result = prepare(client, auth_headers).json()
    assert confirm(client, auth_headers, result).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    def fail_transaction(**kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr("app.services.transfer_service.Transaction", fail_transaction)
    with pytest.raises(RuntimeError):
        execute_transfer(user_id, result["transfer_id"])
    assert balance() == 500000
    with Session(get_engine()) as session:
        assert session.get(TransferRequest, result["transfer_id"]).status == "pending"


def test_concurrent_prepare_creates_one_action_and_one_token(client, auth_headers):
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    request = PrepareTransferRequest.model_validate(payload())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: prepare_transfer(user_id, request), range(2)))
    assert results[0]["transfer_id"] == results[1]["transfer_id"]
    assert sum(item["confirmation_token"] is not None for item in results) == 1
    with Session(get_engine()) as session:
        assert len(session.exec(select(TransferRequest)).all()) == 1
        assert len(session.exec(select(PendingAction)).all()) == 1


def test_confirmed_but_expired_transfer_cannot_execute(client, auth_headers):
    result = prepare(client, auth_headers).json()
    assert confirm(client, auth_headers, result).status_code == 200
    with Session(get_engine()) as session:
        action = session.get(PendingAction, result["action_id"])
        action.expires_at = utcnow() - timedelta(seconds=1)
        session.add(action)
        session.commit()
    assert client.post(f"/api/transfers/{result['transfer_id']}/execute", headers=auth_headers).status_code == 400
    assert balance() == 500000


def test_concurrent_transfers_cannot_exceed_daily_limit(client, auth_headers):
    first = prepare(client, auth_headers, payload(key="a" * 16, amount=60000)).json()
    second = prepare(client, auth_headers, payload(key="b" * 16, amount=60000)).json()
    assert confirm(client, auth_headers, first).status_code == 200
    assert confirm(client, auth_headers, second).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id

    def run(transfer_id):
        try:
            return execute_transfer(user_id, transfer_id)
        except TransferError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [first["transfer_id"], second["transfer_id"]]))
    assert sum(result is not None for result in results) == 1
    assert balance() == 440000
