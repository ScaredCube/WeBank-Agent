"""Failure-boundary tests. Offline deterministic model; no real LLM or bank network."""
import asyncio
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, ChatSubmission, Contact, Message, PendingAction, TransferRequest, User
from app.schemas.chat import ChatRequest, AccountReference, ContactReference
from app.api.routes.chat import send_message


def _events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _new_conversation(client, headers):
    response = client.post("/api/chat/conversations", headers=headers, json={})
    assert response.status_code == 201
    return response.json()["id"]


def _endpoint(conversation_id):
    return f"/api/chat/conversations/{conversation_id}/messages"


def _status(client, headers, cid, request_id):
    result = client.get(f"/api/chat/conversations/{cid}/requests/{request_id}", headers=headers)
    assert result.status_code == 200
    return result.json()


class _DisconnectedRequest:
    async def is_disconnected(self):
        return True


async def _simulate_dropped_sse(conversation_id, payload):
    # Drive the real route and event generator directly so the ASGI test client
    # cannot consume or mask the injected socket-disconnect moment.
    with Session(get_engine()) as db:
        user = db.exec(select(User).where(User.username == "demo")).one()
        response = await send_message(conversation_id, payload, _DisconnectedRequest(), db, user)
        try:
            async for _ in response.body_iterator:
                raise AssertionError("A disconnected client must not receive any events")
        except asyncio.CancelledError:
            return
        raise AssertionError("Disconnected stream unexpectedly completed normally")


def test_disconnect_during_reply_never_marks_request_completed(client, auth_headers, monkeypatch):
    class EchoModel:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            yield LLMChunk(content="model finished but socket is gone")

    llm = EchoModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    cid = _new_conversation(client, auth_headers)
    payload = ChatRequest(content="检查状态", request_id="req-disconnect-readonly-01")
    asyncio.run(_simulate_dropped_sse(cid, payload))
    assert _status(client, auth_headers, cid, payload.request_id)["state"] == "interrupted"
    assert client.post(_endpoint(cid), headers=auth_headers,
                       json=payload.model_dump()).status_code == 409
    assert llm.calls == 1
    with Session(get_engine()) as db:
        attempts = db.exec(select(ChatSubmission)).all()
        assert len(attempts) == 1 and attempts[0].state == "interrupted"
        assert db.exec(select(Message).where(Message.role == "assistant")).all() == []


def test_disconnect_after_transfer_preparation_does_not_reissue_token_or_charge(
    client, auth_headers, monkeypatch,
):
    class PrepareModel:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            yield LLMChunk(tool_calls=[{"id": "call_pending_safe", "type": "function",
                "function": {"name": "prepare_transfer", "arguments": json.dumps({
                    "amount_fen": 100, "source_token": "model_fake_source",
                    "recipient_contact_token": "model_fake_contact",
                    "recipient_name": "model_fake_recipient",
                })}}])

    llm = PrepareModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    with Session(get_engine()) as db:
        account = db.exec(select(Account)).first()
        contact = db.exec(select(Contact)).first()
        account_id, contact_id, opening_balance = account.id, contact.id, account.balance_fen
    cid = _new_conversation(client, auth_headers)
    request_id = "req-disconnect-prepared-01"
    payload = ChatRequest(
        content="从所选账户向所选联系人模拟转账 1 元，先准备待确认操作",
        request_id=request_id,
        references=[AccountReference(kind="account", id=account_id),
                    ContactReference(kind="contact", id=contact_id)],
    )
    asyncio.run(_simulate_dropped_sse(cid, payload))
    status = _status(client, auth_headers, cid, request_id)
    assert status["state"] == "interrupted"
    assert "confirmation_token" not in json.dumps(status)
    assert client.post(_endpoint(cid), headers=auth_headers,
                       json=payload.model_dump()).status_code == 409
    assert llm.calls == 1
    with Session(get_engine()) as db:
        pending = db.exec(select(TransferRequest)).all()
        assert len(pending) == 1 and pending[0].status == "pending"
        assert db.get(Account, account_id).balance_fen == opening_balance
        assert len(db.exec(select(PendingAction)).all()) == 1


def test_model_timeout_is_a_failed_not_retriable_submitted_request(
    client, auth_headers, monkeypatch,
):
    class TimeoutModel:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            raise TimeoutError("synthetic model timeout")
            yield LLMChunk(content="unreachable")  # pragma: no cover

    llm = TimeoutModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    cid = _new_conversation(client, auth_headers)
    payload = {"content": "查询本月账单", "request_id": "req-llm-timeout-01"}
    result = _events(client.post(_endpoint(cid), headers=auth_headers, json=payload))
    assert [entry["type"] for entry in result] == ["error"]
    assert _status(client, auth_headers, cid, payload["request_id"])["state"] == "failed"
    assert client.post(_endpoint(cid), headers=auth_headers, json=payload).status_code == 409
    assert llm.calls == 1
    with Session(get_engine()) as db:
        assert not db.exec(select(TransferRequest)).all()


def test_guard_timeout_escalates_transfer_and_keeps_balance(
    client, auth_headers, monkeypatch,
):
    class TransferModel:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "call_guard_timeout", "type": "function",
                    "function": {"name": "prepare_transfer", "arguments": json.dumps({
                        "amount_fen": 100, "recipient_name": "模拟收款人",
                    })}}])
            else:
                yield LLMChunk(content="I have transferred the money")

    class UnavailableGuard:
        async def review(self, call):
            raise TimeoutError("synthetic guard timeout")

    monkeypatch.setattr("app.agent.loop.get_llm", TransferModel)
    monkeypatch.setattr("app.agent.loop.get_guard", UnavailableGuard)
    with Session(get_engine()) as db:
        opening_balance = db.exec(select(Account)).first().balance_fen
    cid = _new_conversation(client, auth_headers)
    request_id = "req-guard-timeout-01"
    events = _events(client.post(_endpoint(cid), headers=auth_headers, json={
        "content": "给模拟收款人转账1元", "request_id": request_id,
    }))
    action = next(entry for entry in events if entry["type"] == "action_required")
    assert action["action"]["risk_level"] == "red"
    assert action["action"]["details"]["verification"] == "password"
    assert "transferred the money" not in str(events)
    with Session(get_engine()) as db:
        assert db.exec(select(PendingAction)).one()
        assert db.exec(select(TransferRequest)).one().status == "pending"
        assert db.exec(select(Account)).first().balance_fen == opening_balance
