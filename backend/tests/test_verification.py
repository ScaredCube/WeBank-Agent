from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, PendingAction, User, VerificationSession
from app.risk.engine import RiskDecision
from app.services.action_service import create_pending_action, create_simulated_red_action
from app.services.verification_service import VerificationError, start_verification, verify_code


def red_action():
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        action, token = create_simulated_red_action(
            session, user_id=user.id, action_type="demo", details={"amount_fen": 200000},
            decision=RiskDecision(RiskLevel.RED, ("测试",)),
        )
        return action.id, user.id, token


def test_verification_only_marks_demo_action_verified(client, auth_headers, caplog):
    action_id, _, token = red_action()
    path = f"/api/actions/{action_id}/verification"
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    response = client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                           headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "verified" and "尚未执行" in response.json()["message"]
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 400
    assert client.post(f"/api/actions/{action_id}/confirm", json={"token": token},
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(PendingAction, action_id).status == "verified"
        assert session.get(Account, 1).balance_fen == 500000
        challenge = session.exec(select(VerificationSession)).one()
        assert settings.demo_verification_code not in challenge.code_digest
    assert settings.demo_verification_code not in caplog.text


def test_wrong_code_locks_without_reset_or_execution(client, auth_headers):
    action_id, _, token = red_action()
    path = f"/api/actions/{action_id}/verification"
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    for _ in range(3):
        assert client.post(path + "/verify", json={"token": token, "code": "000000"},
                           headers=auth_headers).status_code == 400
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 400
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        challenge = session.exec(select(VerificationSession)).one()
        assert challenge.status == "locked" and challenge.attempts == 3
        assert session.get(PendingAction, action_id).status == "pending"
        assert session.get(Account, 1).balance_fen == 500000


def test_verify_user_token_expiry_and_yellow_isolation(client, auth_headers):
    action_id, user_id, token = red_action()
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
        yellow, yellow_token = create_pending_action(session, user_id=user_id, action_type="demo",
                                                     details={}, decision=RiskDecision(RiskLevel.YELLOW, ()))
        yellow_id = yellow.id
    path = f"/api/actions/{action_id}/verification"
    assert client.post(path + "/start", json={"token": token}).status_code == 401
    assert client.post(path + "/start", json={"token": token}, headers=other_headers).status_code == 400
    assert client.post(path + "/start", json={"token": "x" * 43}, headers=auth_headers).status_code == 400
    assert client.post(f"/api/actions/{yellow_id}/verification/start", json={"token": yellow_token},
                       headers=auth_headers).status_code == 400
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    with Session(get_engine()) as session:
        challenge = session.exec(select(VerificationSession)).one()
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        session.add(challenge)
        session.commit()
    assert client.post(path + "/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 400


def test_verification_is_unavailable_when_debug_disabled(client, auth_headers, monkeypatch):
    action_id, _, token = red_action()
    monkeypatch.setattr(settings, "debug", False)
    assert client.post(f"/api/actions/{action_id}/verification/start", json={"token": token},
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        with pytest.raises(ValueError):
            create_simulated_red_action(session, user_id=1, action_type="demo", details={},
                                        decision=RiskDecision(RiskLevel.RED, ()))


def test_concurrent_wrong_attempts_lock_at_three(client):
    action_id, user_id, token = red_action()
    start_verification(user_id, action_id, token)
    def attempt(_):
        try:
            return verify_code(user_id, action_id, token, "000000")
        except VerificationError:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert not any(executor.map(attempt, range(4)))
    with Session(get_engine()) as session:
        challenge = session.exec(select(VerificationSession)).one()
        assert challenge.status == "locked" and challenge.attempts == 3


def test_cancelled_action_cannot_be_verified(client, auth_headers):
    action_id, _, token = red_action()
    path = f"/api/actions/{action_id}"
    assert client.post(path + "/verification/start", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(path + "/cancel", headers=auth_headers).status_code == 200
    assert client.post(path + "/verification/verify", json={"token": token, "code": settings.demo_verification_code},
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(PendingAction, action_id).status == "cancelled"
        assert session.get(Account, 1).balance_fen == 500000
