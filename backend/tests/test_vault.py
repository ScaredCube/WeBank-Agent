import base64
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, User


@pytest.fixture
def vault_keys(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", base64.urlsafe_b64encode(b"a" * 32).decode())
    monkeypatch.setattr(settings, "data_hmac_key", base64.urlsafe_b64encode(b"b" * 32).decode())
    monkeypatch.setattr(settings, "data_encryption_key_version", "v1")
    monkeypatch.setattr(settings, "data_encryption_previous_keys", "{}")


def test_vault_enforces_owner_type_request_expiry_and_revocation(client, vault_keys):
    from app.services.vault import VaultError, create_temporary, create_account_token, resolve, revoke
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        account = session.exec(select(Account).where(Account.user_id == user.id)).one()
        other = User(username="other", password_hash="x", display_name="other")
        session.add(other)
        session.flush()
        token = create_temporary(session, user.id, "phone_input", "13900000000", "request-one")
        stable = create_account_token(session, user.id, account.id)
        session.commit()
        assert resolve(session, user.id, token, "phone_input", "request-one") == "13900000000"
        assert resolve(session, user.id, stable, "account", "ignored") == account.id
        for actor, value, kind, scope in ((other.id, token, "phone_input", "request-one"),
                (user.id, token, "account", "request-one"), (user.id, token, "phone_input", "request-two"),
                (user.id, "<PHONE_TMP_forged>", "phone_input", "request-one")):
            with pytest.raises(VaultError, match="引用不可用"):
                resolve(session, actor, value, kind, scope)
        from app.models import DataToken
        row = session.exec(select(DataToken).where(DataToken.token == token)).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.add(row); session.flush()
        with pytest.raises(VaultError, match="引用不可用"):
            resolve(session, user.id, token, "phone_input", "request-one")
        revoke(session, user.id, stable)
        with pytest.raises(VaultError, match="引用不可用"):
            resolve(session, user.id, stable, "account", "ignored")


def test_user_supplied_number_is_preserved_in_chat_storage_and_model(client, auth_headers, monkeypatch):
    import json
    from app.agent.llm import LLMChunk
    from app.models import Conversation, Message
    captured = []
    class FakeLLM:
        async def stream(self, messages, tools=None):
            captured.append(json.dumps(messages, ensure_ascii=False))
            yield LLMChunk(content="不使用")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    with Session(get_engine()) as session:
        conversation = session.get(Conversation, conversation_id)
        conversation.title = "旧标题 13900000000"
        session.add(conversation)
        session.add(Message(conversation_id=conversation_id, role="user", content="旧号码 13900000000"))
        session.commit()
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           json={"content": "新号码 13900000000"}, headers=auth_headers)
    history = client.get(f"/api/chat/conversations/{conversation_id}/messages", headers=auth_headers)
    listing = client.get("/api/chat/conversations", headers=auth_headers)
    assert response.status_code == history.status_code == listing.status_code == 200
    assert captured and "13900000000" in captured[0]
    assert "<PHONE_TMP_" in captured[0]
    assert "13900000000" in history.text and "13900000000" in listing.text
    with Session(get_engine()) as session:
        recent = session.exec(select(Message).where(
            Message.conversation_id == conversation_id, Message.role == "user"
        ).order_by(Message.id.desc())).first()
        assert "13900000000" in recent.content


def test_key_rotation_missing_and_damaged_ciphertext_fail_closed(client, vault_keys, monkeypatch):
    import json
    from app.models import DataToken
    from app.services.vault import VaultError, create_temporary, resolve
    old_key = settings.data_encryption_key
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        token = create_temporary(session, user.id, "phone_input", "13900000000", "scope")
        session.commit()
        row = session.exec(select(DataToken).where(DataToken.token == token)).one()
        assert "13900000000" not in row.ciphertext
        new_key = base64.urlsafe_b64encode(b"c" * 32).decode()
        monkeypatch.setattr(settings, "data_encryption_key", new_key)
        monkeypatch.setattr(settings, "data_encryption_key_version", "v2")
        with pytest.raises(VaultError):
            resolve(session, user.id, token, "phone_input", "scope")
        monkeypatch.setattr(settings, "data_encryption_previous_keys", json.dumps({"v1": old_key}))
        assert resolve(session, user.id, token, "phone_input", "scope") == "13900000000"
        assert row.key_version == "v2"
        row.ciphertext = row.ciphertext[:-8] + "damaged!"
        session.add(row); session.flush()
        with pytest.raises(VaultError):
            resolve(session, user.id, token, "phone_input", "scope")
        monkeypatch.setattr(settings, "data_encryption_key", "")
        with pytest.raises(VaultError):
            create_temporary(session, user.id, "phone_input", "13900000000", "scope")


def test_model_tool_definitions_do_not_accept_plain_sensitive_fields():
    from app.tools.register import create_agent_registry
    tools = {spec["function"]["name"]: spec["function"]["parameters"] for spec in create_agent_registry().definitions()}
    assert "execute_transfer" not in tools
    transfer = tools["prepare_transfer"]["properties"]
    assert "recipient_phone" not in transfer and "account_id" not in transfer
    assert "source_token" in transfer and "target_token" in transfer
    balance = tools["get_account_balance"]["properties"]
    assert "account_token" in balance and "account_id" not in balance


def test_revoked_reference_after_prepare_cannot_debit(client, auth_headers, vault_keys, monkeypatch):
    from datetime import timezone
    from app.models import TransferTokenBinding
    from app.services.vault import revoke
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)
    response = client.post("/api/transfers/prepare", headers=auth_headers, json={
        "account_id": 1, "recipient_name": "模拟收款人", "recipient_phone": "13900000000",
        "amount_fen": 50000, "idempotency_key": "vault_test_000001"})
    assert response.status_code == 200
    prepared = response.json()
    assert client.post(f"/api/actions/{prepared['action_id']}/confirm", headers=auth_headers,
                       json={"token": prepared["confirmation_token"]}).status_code == 200
    with Session(get_engine()) as session:
        from app.models import DataToken
        binding = session.get(TransferTokenBinding, prepared["transfer_id"])
        target = session.get(DataToken, binding.target_token_id)
        user_id = target.user_id
        revoke(session, user_id, target.token)
        session.commit()
    response = client.post(f"/api/transfers/{prepared['transfer_id']}/execute", headers=auth_headers)
    assert response.status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
    audit = client.get("/api/audit", headers=auth_headers).json()
    assert {e["event_type"] for e in audit} >= {"token_resolved", "token_revoked", "token_resolve_denied"}
    assert any(e["event_type"] == "token_revoked" and e["reference_id"] and e["entity_kind"] == "phone_input" for e in audit)
    assert "13900000000" not in str(audit) and prepared["confirmation_token"] not in str(audit)


def test_legacy_upgrade_creates_a_separate_scrubbed_copy(tmp_path):
    import sqlite3
    from scripts.redact_legacy_copy import migrate
    source, dest = tmp_path / "old.sqlite", tmp_path / "safe.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("create table message (id integer primary key, content text)")
        db.execute("insert into message values (?, ?)", (1, "号码 13900000000"))
    migrate(source, dest)
    with sqlite3.connect(source) as db:
        assert "13900000000" in db.execute("select content from message").fetchone()[0]
    with sqlite3.connect(dest) as db:
        assert "13900000000" not in db.execute("select content from message").fetchone()[0]
    with pytest.raises(FileExistsError):
        migrate(source, dest)


def test_model_generated_sensitive_tool_arguments_are_not_replayed(client, auth_headers, monkeypatch):
    import json
    from app.agent.llm import LLMChunk
    captured = []
    class FakeLLM:
        async def stream(self, messages, tools=None):
            captured.append(json.dumps(messages, ensure_ascii=False))
            if len(captured) == 1:
                yield LLMChunk(content="13900000000", tool_calls=[{"id": "one", "type": "function", "function": {
                    "name": "get_account_balance", "arguments": '{"account_token":"13900000000"}'}}])
            else:
                yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           json={"content": "查询余额"}, headers=auth_headers)
    assert len(captured) == 2
    assert "13900000000" not in captured[1] and "13900000000" not in response.text


def test_auto_title_and_raw_user_numbers_are_preserved(client, auth_headers, monkeypatch):
    from app.agent.llm import LLMChunk
    seen = []
    class FakeLLM:
        async def stream(self, messages, tools=None):
            seen.append(messages)
            yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"
    client.post(url, json={"content": "联系 13900000000"}, headers=auth_headers)
    assert "13900000000" in client.get("/api/chat/conversations", headers=auth_headers).text
    assert "13900000000" in str(seen)
    invalid = client.post(url, json={"content": "13900000000" * 500}, headers=auth_headers)
    assert invalid.status_code == 422
    previous = len(seen)
    response = client.post(url, json={"content": "请核对 123/456/789/0123456"}, headers=auth_headers)
    assert response.status_code == 200 and len(seen) == previous + 1
    assert "123/456/789/0123456" in str(seen[-1])
    response = client.post(url, json={"content": "号码一三九零零零零零零零零"}, headers=auth_headers)
    assert len(seen) == previous + 2
    assert "一三九零零零零零零零零" in str(seen[-1])
    history = client.get(url, headers=auth_headers).text
    assert "123/456/789/0123456" in history and "一三九零零零零零零零零" in history
