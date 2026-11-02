import re
from datetime import datetime
import json
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, Message, TransferRequest
from sqlmodel import select


@pytest.fixture(autouse=True)
def daytime_policy(monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def send(client, headers, conversation_id, content):
    return client.post(f"/api/chat/conversations/{conversation_id}/messages",
                       json={"content": content}, headers=headers)


def test_agent_prepares_transfer_without_revealing_token_to_model(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        messages_seen = None
        prepared = False

        async def stream(self, messages, tools=None):
            self.calls += 1
            self.messages_seen = json.dumps(messages, ensure_ascii=False)
            if self.prepared or tools is None:
                yield LLMChunk(content="已准备待确认转账。")
                return
            self.prepared = True
            yield LLMChunk(tool_calls=[{"id": "call-1", "type": "function", "function": {
                "name": "prepare_transfer", "arguments": json.dumps({
                    "recipient_name": "模拟收款人", "target_token": re.search(r"<PHONE_TMP_[^>]+>", messages[-1]["content"]).group(), "amount_fen": 50000,
                }, ensure_ascii=False),
            }}])

    llm = FakeLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = send(client, auth_headers, conversation["id"], "给模拟收款人 13812345678 转账500元")
    assert response.headers["cache-control"] == "no-store"
    received = events(response)
    assert [item["type"] for item in received] == ["action_required", "done"]
    action = received[0]
    token = action["confirmation_token"]
    assert action["action"]["details"]["amount_fen"] == 50000
    datetime.fromisoformat(action["action"]["created_at"].replace("Z", "+00:00"))
    assert action["action"]["details"]["recipient_phone_masked"] == "138****5678"

    assert token not in llm.messages_seen and llm.calls == 1
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
        assert all(token not in message.content for message in session.exec(select(Message)).all())

    class TextOnlyLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="我已经替你确认转账。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: TextOnlyLLM())
    send(client, auth_headers, conversation["id"], "确认")
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
        assert session.get(TransferRequest, action["transfer_id"]).status == "pending"
    confirm = client.post(f"/api/actions/{action['action']['id']}/confirm", json={"token": token},
                          headers=auth_headers)
    assert confirm.status_code == 200
    execute = client.post(f"/api/transfers/{action['transfer_id']}/execute", headers=auth_headers)
    assert execute.status_code == 200 and execute.json()["balance_fen"] == 450000


def test_agent_creates_red_transfer_without_executing(client, auth_headers, monkeypatch):
    class FakeLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id": "call-1", "type": "function", "function": {
                "name": "prepare_transfer", "arguments": json.dumps({
                    "recipient_name": "模拟收款人", "amount_fen": 100001,
                }, ensure_ascii=False),
            }}])

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = send(client, auth_headers, conversation["id"], "模拟大额转账")
    action = events(response)[0]
    assert action["type"] == "action_required" and action["action"]["risk_level"] == "red"
    assert client.post(f"/api/transfers/{action['transfer_id']}/execute", headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000


@pytest.mark.parametrize("arguments", [
    {"recipient_name": "模拟收款人", "amount_fen": 50000, "user_id": 99},
    {"recipient_name": "模拟收款人", "amount_fen": 50000, "idempotency_key": "attacker_key"},
])
def test_agent_cannot_prepare_spoofed_transfers(client, auth_headers, monkeypatch, arguments):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "call-1", "type": "function", "function": {
                    "name": "prepare_transfer", "arguments": json.dumps(arguments, ensure_ascii=False),
                }}])
            else:
                yield LLMChunk(content="已成功转账。")

    monkeypatch.setattr(settings, "reply_grounding_enabled", True)
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = send(client, auth_headers, conversation["id"], "模拟转账")
    assert "action_required" not in [item["type"] for item in events(response)]
    assert "已成功转账" not in response.text
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
        assert not session.exec(select(TransferRequest)).all()
