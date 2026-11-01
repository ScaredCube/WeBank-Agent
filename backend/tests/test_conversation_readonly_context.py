"""Prior user bank selections support READ-ONLY follow-ups, not permissions."""
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Card, ConversationSelection, Message, MessageResult
from app.services.conversation_context import allow_readonly_followup, latest_trusted_bill_month


def events_for(response):
    assert response.status_code == 200
    return [json.loads(row[6:]) for row in response.text.splitlines() if row.startswith("data: ")]


def conversation(client, headers):
    r = client.post("/api/chat/conversations", json={}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def send(client, headers, cid, content, references=None):
    return client.post(f"/api/chat/conversations/{cid}/messages", headers=headers,
                       json={"content": content, "references": references or []})


def test_account_selection_survives_reload_and_followup_binds_same_account(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as db:
        account = db.exec(select(Account)).first()
        aid, account_mask = account.id, account.masked_number

    class MultiTurnBill:
        call = 0
        observed_followup = ""
        async def stream(self, messages, tools=None):
            self.call += 1
            if self.call == 1:
                yield LLMChunk(tool_calls=[{"id": "call_initialabc", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'}}])
            elif self.call == 2:
                self.observed_followup = messages[-1]["content"]
                yield LLMChunk(tool_calls=[
                    {"id": "call_followabc", "type": "function",
                     "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'}},
                    {"id": "call_followdef", "type": "function",
                     "function": {"name": "get_monthly_bill", "arguments": '{"month":"2025-12"}'}},
                ])
            else:
                yield LLMChunk(content="Done")
    fake = MultiTurnBill()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: fake)
    cid = conversation(client, auth_headers)
    initial = events_for(send(client, auth_headers, cid, "查询 2026-01 账单",
                              [{"kind": "account", "id": aid}]))
    assert "bill_result" in [e["type"] for e in initial]
    with Session(get_engine()) as db:
        saved = db.get(ConversationSelection, cid)
        assert saved is not None and saved.account_id == aid and saved.card_id is None
        assert latest_trusted_bill_month(db, conversation_id=cid) == ("2026-01", account_mask)

    followup = events_for(send(client, auth_headers, cid, "那相比上个月呢？"))
    assert "bill_result" in [event["type"] for event in followup]
    assert "上个月" in fake.observed_followup
    assert "2026-01" in fake.observed_followup
    history = client.get(f"/api/chat/conversations/{cid}/messages", headers=auth_headers).json()
    assert [item["bill_result"]["month"] for item in history if item["bill_result"]] == ["2026-01", "2026-01"]
    assert [item["data"]["month"] for item in history[-1]["tool_results"]] == ["2026-01", "2025-12"]
    assert "消费" in history[-1]["content"]
    assert "account_token=" not in history[-2]["content"]
    with Session(get_engine()) as db:
        assert len(db.exec(select(MessageResult)).all()) == 2


def test_implicit_card_context_is_readonly_and_session_scoped(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        card = db.exec(select(Card)).first()
        card_id = card.id

    class StatusModel:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_cardabc", "type":"function",
                "function":{"name":"get_card_status","arguments":json.dumps({
                    "card_id": 99999, "account_token":"forged_model_value",
                })}}])
    monkeypatch.setattr("app.agent.loop.get_llm", StatusModel)
    cid = conversation(client, auth_headers)
    assert "card_result" in [e["type"] for e in events_for(send(client, auth_headers, cid,
        "查询所选卡片状态", [{"kind":"card","id":card_id}]))]
    with Session(get_engine()) as db:
        assert db.get(ConversationSelection, cid).card_id == card_id

    next_response = events_for(send(client, auth_headers, cid, "再查一下这张银行卡状态"))
    assert "card_result" in [e["type"] for e in next_response]
    other_cid = conversation(client, auth_headers)
    other_response = events_for(send(client, auth_headers, other_cid, "再查一下这张银行卡状态"))
    assert "card_result" not in [e["type"] for e in other_response]
    with Session(get_engine()) as db:
        assert db.get(ConversationSelection, other_cid) is None


def test_stale_or_revoked_selection_requires_reselection(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        account = db.exec(select(Account)).first()
        aid = account.id

    class ReadOnlyModel:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_abc", "type":"function",
                "function":{"name":"get_monthly_bill","arguments":'{"month":"2026-01"}'}}])
    monkeypatch.setattr("app.agent.loop.get_llm", ReadOnlyModel)
    cid = conversation(client, auth_headers)
    events_for(send(client, auth_headers, cid, "查询 2026-01 账单",
                    [{"kind":"account","id":aid}]))
    with Session(get_engine()) as db:
        account = db.get(Account,aid)
        account.status = "frozen"
        db.add(account)
        db.commit()

    response = send(client, auth_headers, cid, "再查本月账单")
    assert response.status_code == 400
    assert "重新选择" in response.json()["detail"]


def test_cached_selection_cannot_authorize_prepare_operations(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        aid = db.exec(select(Account)).first().id
    class FakeLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_safeb", "type":"function",
                "function":{"name":"get_monthly_bill","arguments":'{"month":"2026-01"}'}}])
    monkeypatch.setattr("app.agent.loop.get_llm", FakeLLM)
    cid=conversation(client,auth_headers)
    events_for(send(client,auth_headers,cid,"查询账单",[{"kind":"account","id":aid}]))
    with Session(get_engine()) as db:
        prior = db.get(ConversationSelection,cid)
        assert prior is not None and prior.account_id == aid
    assert not allow_readonly_followup("把刚才的账户转账 1 元")
    assert not allow_readonly_followup("把银行卡挂失")
    assert not allow_readonly_followup("换个账户查询账单")
    assert allow_readonly_followup("那上个月呢？")

def test_guard_unavailable_does_not_block_readonly_bill(client, auth_headers, monkeypatch):
    from app.models import AuditLog, TransferRequest

    with Session(get_engine()) as db:
        account_id = db.exec(select(Account)).first().id

    class AlwaysTryLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_guardtest", "type":"function",
                "function":{"name":"get_monthly_bill","arguments":'{"month":"2026-01"}'}}])

    class UnavailableGuard:
        async def review(self, call):
            raise RuntimeError("simulated outage")

    monkeypatch.setattr("app.agent.loop.get_llm", AlwaysTryLLM)
    monkeypatch.setattr("app.agent.loop.get_guard", lambda: UnavailableGuard())
    cid = conversation(client,auth_headers)
    events=events_for(send(client,auth_headers,cid,"查询2026-01账单",
        [{"kind":"account","id":account_id}]))
    assert any(item["type"]=="bill_result" for item in events)
    with Session(get_engine()) as db:
        failures=db.exec(select(AuditLog).where(AuditLog.event_type=="guard_failed")).all()
        assert failures
        assert not db.exec(select(TransferRequest)).all()


def test_provider_failure_after_first_trusted_result_keeps_snapshot(
    client,auth_headers,monkeypatch,
):
    with Session(get_engine()) as db:
        aid = db.exec(select(Account)).first().id

    class ProviderDownAfterTool:
        calls = 0
        async def stream(self,messages,tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id":"call_firstabc","type":"function",
                    "function":{"name":"get_monthly_bill","arguments":'{"month":"2026-01"}'}}])
            else:
                raise ConnectionError("simulated model network interruption")
                yield LLMChunk(content="unused")  # pragma: no cover

    monkeypatch.setattr("app.agent.loop.get_llm",ProviderDownAfterTool)
    cid = conversation(client,auth_headers)
    events=events_for(send(client,auth_headers,cid,
        "查询这张银行卡状态和 2026-01 账单",
        [{"kind":"account","id":aid}]))
    assert [event["type"] for event in events] == ["bill_result","delta","done"]
    messages=client.get(f"/api/chat/conversations/{cid}/messages",
                        headers=auth_headers).json()
    assert messages[-1]["tool_results"][0]["kind"]=="monthly_bill"
    assert "部分查询" in messages[-1]["content"]
