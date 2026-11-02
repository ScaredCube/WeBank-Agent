import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (
    Account, AuditLog, Subscription, SubscriptionCancelRequest, Transaction, User,
)
from app.services.subscription_service import execute_cancel


def _sse_payloads(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def _other_headers(session: Session) -> dict:
    other = User(username="subscription_other", password_hash="test", display_name="其他")
    session.add(other)
    session.commit()
    session.refresh(other)
    return {"Authorization": f"Bearer {create_access_token(str(other.id))}"}


def _prepare(client, headers, subscription_id=1):
    response = client.post(f"/api/subscriptions/{subscription_id}/cancel/prepare",
                           headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _confirm(client, headers, prepared, token=None):
    return client.post(f"/api/actions/{prepared['action_id']}/confirm", headers=headers,
                       json={"token": token or prepared["confirmation_token"]})


def test_bank_subscriptions_read_only_and_isolated(client, auth_headers):
    response = client.get("/api/bank/subscriptions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    first = data[0]
    assert first["merchant"] == "视频会员"
    assert first["amount_fen"] == 2_500
    assert first["renewal_soon"] is True
    assert first["can_cancel"] is True
    assert "subscription_token" not in first
    assert response.headers["cache-control"] == "no-store"

    candidates = client.get("/api/bank/subscriptions/candidates", headers=auth_headers)
    assert candidates.status_code == 200 and candidates.json() == []
    assert client.get("/api/bank/subscriptions").status_code == 401
    assert client.post("/api/bank/subscriptions", headers=auth_headers,
                       json={}).status_code == 405

    with Session(get_engine()) as session:
        other_headers = _other_headers(session)
    assert client.get("/api/bank/subscriptions", headers=other_headers).json() == []


def test_detect_subscription_candidates(client, auth_headers):
    now = utcnow()
    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        for index, days in enumerate((70, 10), 1):
            session.add(Transaction(
                account_id=account.id, reference=f"detect-{index}", direction="expense",
                amount_fen=1_999, balance_after_fen=account.balance_fen,
                counterparty="演示订阅服务", category="消费", note="模拟交易",
                occurred_at=now - timedelta(days=days)))
        session.commit()
    response = client.get("/api/bank/subscriptions/candidates", headers=auth_headers)
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 1
    assert candidates[0]["merchant"] == "演示订阅服务"
    assert candidates[0]["amount_fen"] == 1_999
    assert candidates[0]["occurrences"] == 2


def test_cancel_subscription_requires_yellow_confirmation(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    assert prepared["risk_level"] == "yellow"
    assert prepared["confirmation_token"]
    execute_path = f"/api/subscriptions/cancel/{prepared['action_id']}/execute"
    assert client.post(execute_path, headers=auth_headers).status_code == 400
    assert _confirm(client, auth_headers, prepared, "0" * 43).status_code == 400
    assert client.post(execute_path, headers=auth_headers).status_code == 400
    assert _confirm(client, auth_headers, prepared).status_code == 200
    result = client.post(execute_path, headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "cancelled"
    assert client.post(execute_path, headers=auth_headers).json() == result.json()

    subscriptions = client.get("/api/bank/subscriptions", headers=auth_headers).json()
    item = next(entry for entry in subscriptions if entry["subscription_id"] == 1)
    assert item["status"] == "cancelled" and item["can_cancel"] is False
    assert client.post("/api/subscriptions/1/cancel/prepare",
                       headers=auth_headers).status_code == 400
    assert client.get(f"/api/actions/{prepared['action_id']}",
                      headers=auth_headers).json()["status"] == "completed"
    with Session(get_engine()) as session:
        logs = session.exec(select(AuditLog).where(
            AuditLog.event_type == "subscription_cancelled")).all()
        assert len([log for log in logs if log.result == "success"]) == 1


def test_cancel_subscription_owner_isolation(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    with Session(get_engine()) as session:
        other_headers = _other_headers(session)
    assert client.post("/api/subscriptions/1/cancel/prepare",
                       headers=other_headers).status_code == 400
    assert _confirm(client, other_headers, prepared).status_code == 400
    assert client.post(f"/api/subscriptions/cancel/{prepared['action_id']}/execute",
                       headers=other_headers).status_code == 400
    assert _confirm(client, auth_headers, prepared).status_code == 200


def test_agent_can_list_subscriptions_and_prepare_cancel(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "subs", "type": "function", "function": {
                    "name": "get_subscriptions", "arguments": "{}"}}])
            elif self.calls == 2:
                result = json.loads(messages[-1]["content"])
                token = result["data"][0]["subscription_token"]
                yield LLMChunk(tool_calls=[{"id": "cancel", "type": "function", "function": {
                    "name": "prepare_cancel_subscription",
                    "arguments": json.dumps({"subscription_token": token})}}])
            else:
                yield LLMChunk(content="伪造已取消")

    monkeypatch.setattr(settings, "reply_grounding_enabled", True)
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "帮我查订阅并取消视频会员"})
    events = _sse_payloads(response.text)
    action = next(event for event in events if event["type"] == "action_required")
    assert action["action"]["action_type"] == "subscription_cancel"
    assert action["action"]["risk_level"] == "yellow"
    assert action["subscription_id"] == 1
    assert action["confirmation_token"]
    assert "伪造已取消" not in response.text


def test_agent_subscription_rendering_ignores_model_text(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "subs", "type": "function", "function": {
                    "name": "get_subscriptions", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="已查看订阅列表。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "我的订阅"})
    events = _sse_payloads(response.text)
    done = next((event for event in events if event["type"] == "done"), None)
    assert done is not None, response.text
    assert done["message"]["content"] == "已查看订阅列表。"


def test_model_must_use_subscription_token(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bad", "type": "function", "function": {
                    "name": "prepare_cancel_subscription",
                    "arguments": json.dumps({"subscription_id": 1})}}])
            else:
                yield LLMChunk(content="取消订阅未准备。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "取消订阅"})
    assert "action_required" not in response.text
    assert "取消订阅未准备" in response.text


def test_audit_failure_rolls_back_subscription_cancel(client, auth_headers, monkeypatch):
    prepared = _prepare(client, auth_headers)
    assert _confirm(client, auth_headers, prepared).status_code == 200
    from app.services import subscription_service
    original = subscription_service.record

    def fail_completed(session, **fields):
        if fields["event_type"] == "subscription_cancelled":
            raise RuntimeError("audit unavailable")
        return original(session, **fields)

    monkeypatch.setattr(subscription_service, "record", fail_completed)
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with pytest.raises(RuntimeError):
        execute_cancel(user_id, prepared["action_id"])
    with Session(get_engine()) as session:
        assert session.get(Subscription, 1).status == "active"
        request = session.exec(select(SubscriptionCancelRequest).where(
            SubscriptionCancelRequest.action_id == prepared["action_id"])).one()
        assert request.status == "pending"


def test_subscription_cancel_concurrent_execute_once(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    assert _confirm(client, auth_headers, prepared).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_cancel(user_id, prepared["action_id"]), range(2)))
    assert all(result["status"] == "cancelled" for result in results)
    with Session(get_engine()) as session:
        assert session.get(Subscription, 1).status == "cancelled"
        logs = session.exec(select(AuditLog).where(
            AuditLog.event_type == "subscription_cancelled")).all()
        assert len([log for log in logs if log.result == "success"]) == 1
