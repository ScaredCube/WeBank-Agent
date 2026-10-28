import re
import json
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, AuditLog, User
from app.services.transfer_service import execute_transfer


@pytest.fixture(autouse=True)
def daytime(monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)


def prepare(client, headers, amount=50000, key="audit_key_0000001"):
    return client.post("/api/transfers/prepare", headers=headers, json={"account_id": 1,
        "recipient_name": "模拟收款人", "recipient_phone": "13812345678", "amount_fen": amount,
        "note": "private-note-xyz", "idempotency_key": key})


def logs(client, headers):
    response = client.get("/api/audit", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_chat_transfer_audit_chain_and_retry(client, auth_headers, monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)

    class FakeLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id": "call-1", "type": "function", "function": {
                "name": "prepare_transfer", "arguments": json.dumps({
                    "recipient_name": "模拟收款人", "target_token": re.search(r"<PHONE_TMP_[^>]+>", messages[-1]["content"]).group(),
                    "amount_fen": 50000, "note": "private-note-xyz",
                })}}])

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           json={"content": "敏感输入 13812345678 private-note-xyz"}, headers=auth_headers)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    action = next(item for item in events if item["type"] == "action_required")
    action_id, transfer_id = action["action"]["id"], action["transfer_id"]
    token = action["confirmation_token"]
    assert client.post(f"/api/actions/{action_id}/confirm", json={"token": token}, headers=auth_headers).status_code == 200
    assert client.post(f"/api/transfers/{transfer_id}/execute", headers=auth_headers).status_code == 200
    assert client.post(f"/api/transfers/{transfer_id}/execute", headers=auth_headers).status_code == 200
    response = client.get("/api/audit", headers=auth_headers)
    assert response.status_code == 200
    logs = response.json()
    chain = [event for event in logs if event.get("transfer_id") == transfer_id]
    assert {event["event_type"] for event in chain} >= {
        "transfer_prepared", "risk_assessed", "action_confirmed", "transfer_completed", "transfer_retried"
    }
    assert all(event["conversation_id"] == conversation_id for event in chain)
    assert len([event for event in chain if event["event_type"] == "transfer_completed"]) == 1
    assert all(event["request_id"] for event in chain)
    prepared = next(event for event in chain if event["event_type"] == "transfer_prepared")
    called = next(event for event in logs if event["event_type"] == "tool_called")
    assert prepared["request_id"] == called["request_id"]
    assert len({e["request_id"] for e in chain if e["event_type"] in
                {"transfer_prepared", "action_confirmed", "transfer_completed", "transfer_retried"}}) == 4
    assert token not in response.text and "13812345678" not in response.text and "private-note-xyz" not in response.text


def test_direct_rejection_and_failed_transaction_survive_rollback(client, auth_headers, monkeypatch):
    item = prepare(client, auth_headers).json()
    action, transfer, token = item["action_id"], item["transfer_id"], item["confirmation_token"]
    assert client.post(f"/api/transfers/{transfer}/execute", headers=auth_headers).status_code == 400
    assert client.post(f"/api/actions/{action}/confirm", json={"token": token}, headers=auth_headers).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    def fail_transaction(**kwargs):
        raise RuntimeError("sensitive secret in exception")
    monkeypatch.setattr("app.services.transfer_service.Transaction", fail_transaction)
    with pytest.raises(RuntimeError):
        execute_transfer(user_id, transfer)
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
    entries = [entry for entry in logs(client, auth_headers) if entry["transfer_id"] == transfer]
    assert {entry["event_type"] for entry in entries} >= {"transfer_denied", "transfer_failed"}
    assert all(entry["conversation_id"] is None for entry in entries)
    assert next(e for e in entries if e["event_type"] == "transfer_denied")["reason_codes"] == "not_authorized"
    assert "sensitive secret" not in json.dumps(entries)


def test_isolation_verification_lock_and_no_secrets(client, auth_headers):
    item = prepare(client, auth_headers, amount=100001).json()
    action, token = item["action_id"], item["confirmation_token"]
    path = f"/api/actions/{action}/verification"
    assert client.post(path + "/start", json={"token": token}, headers=auth_headers).status_code == 200
    for _ in range(3):
        assert client.post(path + "/verify", json={"token": token, "code": "909090"}, headers=auth_headers).status_code == 400
    entries = logs(client, auth_headers)
    assert [e["event_type"] for e in entries].count("verification_failed") == 2
    assert any(e["event_type"] == "verification_locked" for e in entries)
    serialized = json.dumps(entries)
    for secret in (token, "909090", "13812345678", "private-note-xyz", auth_headers["Authorization"]):
        assert secret not in serialized
    with Session(get_engine()) as session:
        other = User(username="other", password_hash="test", display_name="其他")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    assert logs(client, other_headers) == []
    assert client.post(f"/api/actions/{action}/cancel", headers=other_headers).status_code == 400
    other_logs = logs(client, other_headers)
    assert len(other_logs) == 1 and other_logs[0]["event_type"] == "action_cancel_denied"
    assert other_logs[0]["action_id"] is None and other_logs[0]["transfer_id"] is None
    assert client.get("/api/audit").status_code == 401


def test_audit_write_failure_prevents_debit(client, auth_headers, monkeypatch):
    item = prepare(client, auth_headers).json()
    assert client.post(f"/api/actions/{item['action_id']}/confirm",
                       json={"token": item["confirmation_token"]}, headers=auth_headers).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    def fail_completed(session, **fields):
        if fields["event_type"] == "transfer_completed":
            raise RuntimeError("audit unavailable")
        from app.services.audit_service import record
        return record(session, **fields)
    monkeypatch.setattr("app.services.transfer_service.record", fail_completed)
    with pytest.raises(RuntimeError):
        execute_transfer(user_id, item["transfer_id"])
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
        assert not session.exec(select(AuditLog).where(AuditLog.event_type == "transfer_completed")).all()
    assert any(e["event_type"] == "transfer_failed" for e in logs(client, auth_headers))


def test_readonly_tool_audits_chat_and_cancellation(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "one", "type": "function", "function": {
                    "name": "get_account_balance", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    client.post(f"/api/chat/conversations/{conversation_id}/messages", json={"content": "查余额"}, headers=auth_headers)
    entries = logs(client, auth_headers)
    assert any(e["tool"] == "get_account_balance" and e["event_type"] == "tool_result"
               and e["conversation_id"] == conversation_id for e in entries)
    item = prepare(client, auth_headers).json()
    assert client.post(f"/api/actions/{item['action_id']}/cancel", headers=auth_headers).status_code == 200
    assert any(e["event_type"] == "action_cancelled" for e in logs(client, auth_headers))


def test_risk_upgrade_is_recorded_after_rejection(client, auth_headers, monkeypatch):
    item = prepare(client, auth_headers).json()
    assert client.post(f"/api/actions/{item['action_id']}/confirm",
                       json={"token": item["confirmation_token"]}, headers=auth_headers).status_code == 200
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", hour)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 1) % 24)
    assert client.post(f"/api/transfers/{item['transfer_id']}/execute", headers=auth_headers).status_code == 400
    chain = [e for e in logs(client, auth_headers) if e["transfer_id"] == item["transfer_id"]]
    assert any(e["event_type"] == "risk_assessed" and e["risk_level"] == "red"
               and "night_upgrade" in e["reason_codes"] for e in chain)
    assert any(e["event_type"] == "transfer_denied" and e["reason_codes"] == "risk_upgrade" for e in chain)


def test_red_verification_and_transfer_success_are_recorded(client, auth_headers):
    item = prepare(client, auth_headers, amount=100001).json()
    path = f"/api/actions/{item['action_id']}/verification"
    assert client.post(path + "/start", json={"token": item["confirmation_token"]}, headers=auth_headers).status_code == 200
    assert client.post(path + "/verify", json={"token": item["confirmation_token"],
                       "code": settings.demo_verification_code}, headers=auth_headers).status_code == 200
    assert client.post(f"/api/transfers/{item['transfer_id']}/execute", headers=auth_headers).status_code == 200
    chain = [e for e in logs(client, auth_headers) if e["transfer_id"] == item["transfer_id"]]
    assert {e["event_type"] for e in chain} >= {"verification_started", "verification_succeeded", "transfer_completed"}
    assert settings.demo_verification_code not in json.dumps(chain)


def test_query_tool_exception_records_failure_without_exception_text(client, auth_headers, monkeypatch):
    from app.agent.registry import RiskLevel, ToolRegistry, ToolSpec
    async def fail(**kwargs):
        raise RuntimeError("private-exception-13812345678")
    registry = ToolRegistry()
    registry.register(ToolSpec(name="get_account_balance", description="查询", parameters={},
                               risk=RiskLevel.GREEN, handler=fail))
    class FakeLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id": "one", "type": "function", "function": {
                "name": "get_account_balance", "arguments": "{}"}}])
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    monkeypatch.setattr("app.agent.loop.create_agent_registry", lambda: registry)
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    client.post(f"/api/chat/conversations/{conversation_id}/messages", json={"content": "查询"}, headers=auth_headers)
    entries = logs(client, auth_headers)
    assert any(e["event_type"] == "tool_result" and e["result"] == "failed"
               and e["conversation_id"] == conversation_id for e in entries)
    assert "private-exception" not in json.dumps(entries)
