import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import utcnow
from app.db.seed import seed_demo_cards
from app.db.session import get_engine
from app.models import Account, AuditLog, Card, CardLossRequest, Transaction, TransferRequest, User, VerificationSession
from app.services.card_service import execute_loss
from app.services.transfer_service import TransferError, execute_transfer


def verification(client, headers, action, token, code=None):
    path = f"/api/actions/{action}/verification"
    assert client.post(path + "/start", headers=headers, json={"token": token}).status_code == 200
    response = client.post(path + "/verify", headers=headers,
                           json={"token": token, "code": code or settings.demo_verification_code})
    if response.status_code == 200 and response.json().get("status") == "code_verified":
        response = client.post(path + "/face", headers=headers, json={"token": token})
    return response


def prepare_loss(client, headers):
    response = client.post("/api/cards/1/loss/prepare", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_loss_requires_verification_blocks_prepared_and_new_transfer(client, auth_headers, monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)
    transfer = {"account_id": 1, "recipient_name": "模拟收款人", "amount_fen": 50000,
                "idempotency_key": "pending_before_loss"}
    prepared_transfer = client.post("/api/transfers/prepare", headers=auth_headers, json=transfer).json()
    assert client.post(f"/api/actions/{prepared_transfer['action_id']}/confirm", headers=auth_headers,
                       json={"token": prepared_transfer["confirmation_token"]}).status_code == 200
    loss = prepare_loss(client, auth_headers)
    action, token = loss["action_id"], loss["confirmation_token"]
    path = f"/api/cards/loss/{action}/execute"
    assert client.post(path, headers=auth_headers).status_code == 400
    assert verification(client, auth_headers, action, token, "000000").status_code == 400
    assert client.post(path, headers=auth_headers).status_code == 400
    verify_path = f"/api/actions/{action}/verification/verify"
    assert client.post(verify_path, headers=auth_headers, json={"token": token,
                       "code": settings.demo_verification_code}).status_code == 200
    assert client.post(f"/api/actions/{action}/verification/face", headers=auth_headers,
                       json={"token": token}).status_code == 200
    assert client.get("/api/cards", headers=auth_headers).json()[0]["status"] == "active"
    assert client.post(path, headers=auth_headers).json()["status"] == "lost"
    assert client.post(path, headers=auth_headers).json()["status"] == "lost"
    assert client.get(f"/api/actions/{action}", headers=auth_headers).json()["status"] == "completed"
    assert client.post("/api/cards/1/loss/prepare", headers=auth_headers).status_code == 400
    assert client.post(f"/api/transfers/{prepared_transfer['transfer_id']}/execute", headers=auth_headers).status_code == 400
    transfer["idempotency_key"] = "new_after_loss_000"
    assert client.post("/api/transfers/prepare", headers=auth_headers, json=transfer).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000
        assert session.get(Card, 1).status == "lost"
        user = session.exec(select(User).where(User.username == "demo")).one()
        seed_demo_cards(session, user)
        assert session.get(Card, 1).status == "lost"
        entries = session.exec(select(AuditLog).where(AuditLog.event_type == "card_loss_completed")).all()
        assert len([e for e in entries if e.result == "success"]) == 1


def test_card_owner_isolation_and_disabled_debug(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        other = User(username="card_other", password_hash="test", display_name="其他")
        session.add(other); session.commit(); session.refresh(other)
        headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    assert client.get("/api/cards", headers=headers).json() == []
    assert client.post("/api/cards/1/loss/prepare", headers=headers).status_code == 400
    loss = prepare_loss(client, auth_headers)
    assert client.post(f"/api/cards/loss/{loss['action_id']}/execute", headers=headers).status_code == 400
    monkeypatch.setattr(settings, "debug", False)
    assert client.post("/api/cards/1/loss/prepare", headers=auth_headers).status_code == 400
    assert client.post(f"/api/cards/loss/{loss['action_id']}/execute", headers=auth_headers).status_code == 400


def test_loss_expired_verification_and_unavailable_account(client, auth_headers):
    loss = prepare_loss(client, auth_headers)
    assert verification(client, auth_headers, loss["action_id"], loss["confirmation_token"]).status_code == 200
    with Session(get_engine()) as session:
        challenge = session.exec(select(VerificationSession).where(
            VerificationSession.action_id == loss["action_id"])).one()
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        session.add(challenge); session.commit()
    assert client.post(f"/api/cards/loss/{loss['action_id']}/execute", headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        account.status = "frozen"
        session.add(account); session.commit()
    assert client.post("/api/cards/1/loss/prepare", headers=auth_headers).status_code == 400
    assert client.get("/api/cards", headers=auth_headers).json()[0]["status"] == "active"


def test_failed_audit_rolls_back_card_loss(client, auth_headers, monkeypatch):
    loss = prepare_loss(client, auth_headers)
    assert verification(client, auth_headers, loss["action_id"], loss["confirmation_token"]).status_code == 200
    from app.services import card_service
    original = card_service.record
    def fail_completed(session, **fields):
        if fields["event_type"] == "card_loss_completed":
            raise RuntimeError("audit unavailable")
        return original(session, **fields)
    monkeypatch.setattr(card_service, "record", fail_completed)
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with pytest.raises(RuntimeError):
        execute_loss(user_id, loss["action_id"])
    with Session(get_engine()) as session:
        assert session.get(Card, 1).status == "active"
        assert session.exec(select(CardLossRequest)).one().status == "pending"


def test_card_loss_concurrent_execute_once(client, auth_headers):
    loss = prepare_loss(client, auth_headers)
    assert verification(client, auth_headers, loss["action_id"], loss["confirmation_token"]).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_loss(user_id, loss["action_id"]), range(2)))
    assert all(item["status"] == "lost" for item in results)
    with Session(get_engine()) as session:
        assert session.get(Card, 1).status == "lost"
        assert session.exec(select(CardLossRequest)).one().status == "completed"
        events = session.exec(select(AuditLog).where(AuditLog.event_type == "card_loss_completed")).all()
        assert len([entry for entry in events if entry.result == "success"]) == 1


def test_card_tools_status_and_loss_event(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "card", "type": "function", "function": {
                    "name": "get_card_status", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="伪造卡片状态")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers,
                           json={"content": "查询卡片状态"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[0]["type"] == "card_result"
    assert events[0]["data"]["cards"][0]["status"] == "active"
    assert "account_token" not in response.text and "<CARD_" not in response.text
    assert "伪造卡片状态" not in response.text

    class LossLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id": "loss", "type": "function", "function": {
                "name": "prepare_card_loss", "arguments": "{}"}}])
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: LossLLM())
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers,
                           json={"content": "我要挂失"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    action = next(event for event in events if event["type"] == "action_required")
    assert action["action"]["action_type"] == "card_loss" and action["action"]["risk_level"] == "red"
    assert action["confirmation_token"]
    assert client.get("/api/cards", headers=auth_headers).json()[0]["status"] == "active"


@pytest.mark.parametrize("account_state,expected", [("frozen", "已冻结"), ("unknown", "不可用")])
def test_chat_card_status_shows_account_status(client, auth_headers, monkeypatch, account_state, expected):
    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        account.status = account_state
        session.add(account)
        session.commit()
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "status", "type": "function", "function": {
                    "name": "get_card_status", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="ignored")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=auth_headers,
                           json={"content": "查询卡片状态"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[0]["type"] == "card_result"
    assert events[0]["data"]["cards"][0]["status"] == "active"
    assert events[0]["data"]["cards"][0]["account_status"] == account_state


@pytest.mark.parametrize("first", ["loss", "transfer"])
def test_loss_and_transfer_concurrent_commit_order(client, auth_headers, monkeypatch, first):
    from app.services import card_service, transfer_service
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)
    transfer = client.post("/api/transfers/prepare", headers=auth_headers, json={
        "account_id": 1, "recipient_name": "模拟收款人", "amount_fen": 50000,
        "idempotency_key": "race_loss_transfer"}).json()
    assert client.post(f"/api/actions/{transfer['action_id']}/confirm", headers=auth_headers,
                       json={"token": transfer["confirmation_token"]}).status_code == 200
    loss = prepare_loss(client, auth_headers)
    assert verification(client, auth_headers, loss["action_id"], loss["confirmation_token"]).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    acquired, contender_started = threading.Event(), threading.Event()
    original_begin = card_service._begin if first == "loss" else transfer_service._begin_locked
    def gated_begin(session):
        original_begin(session)
        acquired.set()
        if not contender_started.wait(5):
            raise RuntimeError("concurrent operation did not start")
    monkeypatch.setattr(card_service if first == "loss" else transfer_service,
                        "_begin" if first == "loss" else "_begin_locked", gated_begin)
    def run_loss():
        return execute_loss(user_id, loss["action_id"])
    def run_transfer():
        try:
            return execute_transfer(user_id, transfer["transfer_id"])
        except TransferError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(run_loss if first == "loss" else run_transfer)
        assert acquired.wait(5)
        def run_contender():
            contender_started.set()
            return run_transfer() if first == "loss" else run_loss()
        second_future = pool.submit(run_contender)
        first_result, second_result = first_future.result(timeout=10), second_future.result(timeout=10)
    transfer_result = second_result if first == "loss" else first_result
    assert (transfer_result is None) == (first == "loss")
    with Session(get_engine()) as session:
        assert session.get(Card, 1).status == "lost"
        assert session.get(Account, 1).balance_fen == (500000 if first == "loss" else 450000)
        row = session.get(TransferRequest, transfer["transfer_id"])
        entries = session.exec(select(Transaction).where(Transaction.category == "模拟转账")).all()
        logs = session.exec(select(AuditLog)).all()
        completed = [e for e in logs if e.event_type == "transfer_completed" and e.transfer_id == row.id]
        denied = [e for e in logs if e.event_type == "transfer_denied" and e.transfer_id == row.id]
        card_done = [e for e in logs if e.event_type == "card_loss_completed" and e.action_id == loss["action_id"] and e.result == "success"]
        assert len(card_done) == 1
        if first == "loss":
            assert row.status == "pending" and row.transaction_id is None
            assert not entries and not completed and len(denied) == 1
        else:
            assert row.status == "completed" and len(entries) == len(completed) == 1
            assert row.transaction_id == entries[0].id == completed[0].transaction_id
            assert entries[0].amount_fen == 50000 and not denied
            assert completed[0].id < card_done[0].id
    if transfer_result is not None:
        assert execute_transfer(user_id, transfer["transfer_id"]) == transfer_result


def test_multiple_verified_loss_requests_only_one_succeeds(client, auth_headers):
    first, second = prepare_loss(client, auth_headers), prepare_loss(client, auth_headers)
    assert first["action_id"] != second["action_id"]
    for item in (first, second):
        assert verification(client, auth_headers, item["action_id"], item["confirmation_token"]).status_code == 200
    assert client.post(f"/api/cards/loss/{first['action_id']}/execute", headers=auth_headers).status_code == 200
    refused = client.post(f"/api/cards/loss/{second['action_id']}/execute", headers=auth_headers)
    assert refused.status_code == 400 and "已挂失" in refused.json()["detail"]
    with Session(get_engine()) as session:
        requests = session.exec(select(CardLossRequest).order_by(CardLossRequest.id)).all()
        assert [item.status for item in requests] == ["completed", "pending"]
        logs = session.exec(select(AuditLog)).all()
        assert len([e for e in logs if e.event_type == "card_loss_completed" and e.result == "success"]) == 1
        assert any(e.event_type == "card_loss_denied" and e.action_id == second["action_id"] for e in logs)


def test_selected_card_status_is_exact_and_persisted_without_token(client, auth_headers, monkeypatch):
    from app.models import MessageResult
    from app.services.vault import decrypt_result_snapshot
    from app.schemas.card_results import CardStatusSnapshot
    from app.services.card_service import list_cards
    from app.services.vault import create_account_token

    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        selected = session.exec(select(Card).where(Card.account_id == account.id)).one()
        selected.status = "lost"
        session.add(selected)
        another = Account(user_id=account.user_id, name="另一个账户",
                          masked_number="**** 9999", currency="CNY", balance_fen=600000, status="active")
        session.add(another)
        session.flush()
        session.add(Card(account_id=another.id, status="active"))
        session.commit()
        selected_id = selected.id
        account_token = create_account_token(session, account.user_id, account.id)
        session.commit()
        all_rows = list_cards(session, account.user_id)
        selected_rows = list_cards(session, account.user_id, account_token, selected_id)
        assert len(all_rows) == 2
        assert len(selected_rows) == 1 and selected_rows[0]["card_id"] == selected_id

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                import re
                text = messages[-1]["content"]
                expected_id = int(re.search(r"card_id=(\d+)", text).group(1))
                token = re.search(r"<CARD_[A-Za-z]{32}>", text).group()
                assert expected_id == selected_id
                yield LLMChunk(tool_calls=[{"id": "selected-status", "type": "function", "function": {
                    "name": "get_card_status",
                    "arguments": "{}"}}])  # Model omitted filters; the server must narrow the result.
            else:
                yield LLMChunk(content="模型杜撰的银行卡状态不会被采用。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation}/messages"
    response = client.post(url, headers=auth_headers, json={
        "content": "查询我选中的这张银行卡",
        "references": [{"kind": "card", "id": selected_id}]})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [item["type"] for item in events] == ["card_result", "delta", "done"]
    saved = events[-1]["message"]
    assert saved["card_result"] == {"cards": [{
        "card_id": selected_id,
        "account_name": account.name, "masked_number": account.masked_number,
        "status": "lost", "account_status": "active"}]}
    assert "account_token" not in response.text and "<CARD_" not in response.text

    with Session(get_engine()) as session:
        row = session.exec(select(MessageResult)).one()
        assert row.kind == "card_status" and row.message_id == saved["id"]
        assert "lost" not in row.ciphertext
        assert "account_token" not in row.ciphertext
        assert CardStatusSnapshot.model_validate(decrypt_result_snapshot(
            row.ciphertext, row.key_version)).model_dump() == saved["card_result"]

    history = client.get(url, headers=auth_headers)
    assert history.status_code == 200 and history.headers["cache-control"] == "no-store"
    assert history.json()[-1]["card_result"] == saved["card_result"]
    assert history.json()[0]["card_result"] is None


def test_card_snapshot_rejects_extra_tokens_and_invalid_fields():
    from app.schemas.card_results import CardStatusSnapshot, from_card_tool_result
    from pydantic import ValidationError

    sanitized = from_card_tool_result([{
        "card_id": 1, "account_name": "test", "masked_number": "**** 0001",
        "status": "active", "account_status": "active",
        "account_token": "<CARD_synthetic>", "unsafe_extra": "MUST_NOT_APPEAR"}])
    assert "account_token" not in sanitized.model_dump_json()
    assert "MUST_NOT_APPEAR" not in sanitized.model_dump_json()
    with pytest.raises(ValidationError):
        CardStatusSnapshot.model_validate({"cards": [{
            "card_id": 1, "account_name": "test", "masked_number": "****",
            "status": "active", "account_status": "active",
            "account_token": "<CARD_synthetic>"}]})
