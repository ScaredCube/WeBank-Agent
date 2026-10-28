import json

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.db.session import get_engine
from app.models import Account, DataToken, User
from app.services.vault import VaultError, create_temporary


def test_hmac_and_encryption_keys_must_be_distinct(client, monkeypatch):
    monkeypatch.setattr(settings, "data_hmac_key", settings.data_encryption_key)
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        with pytest.raises(VaultError, match="引用不可用"):
            create_temporary(session, user.id, "phone_input", "13900000000", "scope")
        assert session.exec(select(DataToken)).all() == []


def test_model_cannot_reuse_temporary_reference_from_another_request(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        reference = create_temporary(session, user.id, "phone_input", "13900000000", "other-request")
        session.commit()
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "one", "type": "function", "function": {
                    "name": "prepare_transfer", "arguments": json.dumps({"target_token": reference,
                        "recipient_name": "模拟收款人", "amount_fen": 100})}}])
            else:
                yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers,
                           json={"content": "模拟转账"})
    assert "action_required" not in response.text
    assert "13900000000" not in response.text and reference not in response.text
    entries = client.get("/api/audit", headers=auth_headers).json()
    assert any(e["event_type"] == "token_resolve_denied" for e in entries)
    assert reference not in json.dumps(entries)
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000


def test_synthetic_luhn_card_is_tokenized_before_model_and_storage(client, auth_headers, monkeypatch):
    from app.services.redaction import _luhn
    synthetic = next("999000000000000" + str(n) for n in range(10) if _luhn("999000000000000" + str(n)))
    seen = []
    class FakeLLM:
        async def stream(self, messages, tools=None):
            seen.append(json.dumps(messages, ensure_ascii=False))
            yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers,
                           json={"content": "测试卡号 " + synthetic})
    assert response.status_code == 200 and seen and "<CARD_INPUT_" in seen[0]
    assert synthetic not in seen[0] and synthetic not in response.text
    history = client.get(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers)
    assert synthetic not in history.text
    with Session(get_engine()) as session:
        row = session.exec(select(DataToken).where(DataToken.kind == "card_input")).one()
        assert synthetic not in row.ciphertext
