from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.agent.registry import RiskLevel
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import PendingAction, User
from app.risk.engine import RiskDecision
from app.services.action_service import cancel_pending_action, confirm_pending_action, create_pending_action


def create_action():
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        action, token = create_pending_action(
            session, user_id=user.id, action_type="demo", details={"amount_fen": 500},
            decision=RiskDecision(RiskLevel.YELLOW, ("测试",)),
        )
        assert token not in action.token_hash
        return action.id, user.id, token


def test_confirm_requires_auth_token_and_is_single_use(client, auth_headers):
    action_id, _, token = create_action()
    path = f"/api/actions/{action_id}/confirm"
    assert client.post(path, json={"token": token}).status_code == 401
    assert client.post(path, json={"token": "x" * 43}, headers=auth_headers).status_code == 400
    result = client.post(path, json={"token": token}, headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "confirmed"
    assert "尚未执行" in result.json()["message"]
    assert client.post(path, json={"token": token}, headers=auth_headers).status_code == 400


def test_confirm_rejects_other_user_and_expired_action(client, auth_headers):
    action_id, _, token = create_action()
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_token = create_access_token(str(other.id))
    path = f"/api/actions/{action_id}/confirm"
    assert client.post(path, json={"token": token},
                       headers={"Authorization": f"Bearer {other_token}"}).status_code == 400
    with Session(get_engine()) as session:
        action = session.get(PendingAction, action_id)
        action.expires_at = utcnow() - timedelta(seconds=1)
        session.add(action)
        session.commit()
    assert client.post(path, json={"token": token}, headers=auth_headers).status_code == 400


def test_only_yellow_actions_can_use_confirmation(client):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        with pytest.raises(ValueError):
            create_pending_action(session, user_id=user.id, action_type="demo", details={},
                                  decision=RiskDecision(RiskLevel.RED, ("测试",)))


def test_concurrent_confirm_consumes_token_once(client):
    action_id, user_id, token = create_action()

    def confirm():
        with Session(get_engine()) as session:
            return confirm_pending_action(session, user_id=user_id, action_id=action_id, token=token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: confirm(), range(2)))
    assert sorted(results) == [False, True]


def test_action_details_are_user_scoped_and_do_not_expose_token(client, auth_headers):
    action_id, _, token = create_action()
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    path = f"/api/actions/{action_id}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other_headers).status_code == 404
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["details"] == {"amount_fen": 500}
    assert response.json()["status"] == "pending"
    assert "token_hash" not in response.json() and token not in response.text


def test_cancel_is_owner_only_and_prevents_confirm(client, auth_headers):
    action_id, _, token = create_action()
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    path = f"/api/actions/{action_id}"
    assert client.post(path + "/cancel").status_code == 401
    assert client.post(path + "/cancel", headers=other_headers).status_code == 400
    assert client.post(path + "/cancel", headers=auth_headers).json()["status"] == "cancelled"
    assert client.post(path + "/cancel", headers=auth_headers).status_code == 400
    assert client.post(path + "/confirm", json={"token": token}, headers=auth_headers).status_code == 400
    assert client.get(path, headers=auth_headers).json()["status"] == "cancelled"


def test_expired_and_confirmed_actions_cannot_be_cancelled(client, auth_headers):
    action_id, _, token = create_action()
    path = f"/api/actions/{action_id}"
    with Session(get_engine()) as session:
        action = session.get(PendingAction, action_id)
        action.expires_at = utcnow() - timedelta(seconds=1)
        session.add(action)
        session.commit()
    assert client.get(path, headers=auth_headers).json()["status"] == "expired"
    assert client.post(path + "/cancel", headers=auth_headers).status_code == 400
    assert client.post(path + "/confirm", json={"token": token}, headers=auth_headers).status_code == 400

    action_id, _, token = create_action()
    path = f"/api/actions/{action_id}"
    assert client.post(path + "/confirm", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(path + "/cancel", headers=auth_headers).status_code == 400
    assert client.get(path, headers=auth_headers).json()["status"] == "confirmed"


def test_confirm_and_cancel_race_only_one_succeeds(client):
    action_id, user_id, token = create_action()

    def run(operation):
        with Session(get_engine()) as session:
            if operation == "confirm":
                return confirm_pending_action(session, user_id=user_id, action_id=action_id, token=token)
            return cancel_pending_action(session, user_id=user_id, action_id=action_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, ("confirm", "cancel")))
    assert sorted(results) == [False, True]
