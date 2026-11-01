"""Real-model-derived regressions, all executed with offline fake LLM.

Checks authenticated object binding and partial-result recovery without
weakening Guard, object ownership, or transaction confirmation gates.
"""
import json
from sqlmodel import Session, select
from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Card, MessageResult


def _events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def _conversation(client, headers):
    response = client.post("/api/chat/conversations", headers=headers, json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_authenticated_card_and_bill_override_forged_model_object_ids(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        card = db.exec(select(Card)).first()
        assert card is not None
        card_id = card.id

    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[
                    {"id": "call_safeabc", "type": "function",
                     "function": {"name": "get_card_status", "arguments": json.dumps({
                         "account_token": "forged_by_model", "card_id": 99999})}},
                    {"id": "call_safedef", "type": "function",
                     "function": {"name": "get_monthly_bill", "arguments": json.dumps({
                         "month": "2026-01", "account_token": "forged_by_model"})}},
                ])
            else:
                yield LLMChunk(content="我已经完成查询。")

    monkeypatch.setattr("app.agent.loop.get_llm", FakeLLM)
    cid = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{cid}/messages"
    events = _events(client.post(url, headers=auth_headers, json={
        "content": "查询这张卡状态及关联账户 2026-01 月账单",
        "references": [{"kind": "card", "id": card_id}],
    }))
    kinds = [e["type"] for e in events]
    assert "card_result" in kinds and "bill_result" in kinds and kinds[-1] == "done"
    saved = client.get(url, headers=auth_headers).json()[-1]
    assert sorted(item["kind"] for item in saved["tool_results"]) == ["card_status", "monthly_bill"]
    assert saved["card_result"]["cards"][0]["card_id"] == card_id
    assert saved["bill_result"]["month"] == "2026-01"
    assert "forged_by_model" not in str(saved)
    with Session(get_engine()) as db:
        assert len(db.exec(select(MessageResult)).all()) == 1


def test_agent_error_after_valid_bill_preserves_trusted_partial_history(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        account_id = db.exec(select(Account)).first().id
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id":"call_validabc", "type":"function",
                    "function":{"name":"get_monthly_bill", "arguments":json.dumps({"month":"2026-01"})}}])
            else:
                yield LLMChunk(tool_calls=[{"id":"", "type":"function",
                    "function":{"name":"calculate","arguments":"{}"}}])
    monkeypatch.setattr("app.agent.loop.get_llm", FakeLLM)
    cid = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{cid}/messages"
    events = _events(client.post(url, headers=auth_headers, json={
        "content": "查 2026-01 月账单，并核查银行卡状态", "references":[{"kind":"account","id":account_id}]
    }))
    assert [e["type"] for e in events] == ["bill_result","delta","done"]
    assert events[-1]["message"]["bill_result"]["month"] == "2026-01"
    saved=client.get(url,headers=auth_headers).json()[-1]
    assert saved["tool_results"][0]["kind"]=="monthly_bill"
    assert "部分查询" in saved["content"]

def test_verified_contact_and_account_bind_model_transfer_to_pending_only(client, auth_headers, monkeypatch):
    from app.models import Contact, TransferRequest
    with Session(get_engine()) as db:
        account=db.exec(select(Account)).first()
        contact=db.exec(select(Contact)).first()
        original_balance=account.balance_fen
        account_id,contact_id,contact_name=account.id,contact.id,contact.name

    class FakeLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_safetransfer","type":"function",
                "function":{"name":"prepare_transfer","arguments":json.dumps({
                    "source_token":"fake_source", "recipient_contact_token":"fake_contact",
                    "recipient_name":"wrong_receiver","amount_fen":100
                })}}])
    monkeypatch.setattr("app.agent.loop.get_llm", FakeLLM)
    cid=_conversation(client,auth_headers)
    url=f"/api/chat/conversations/{cid}/messages"
    events=_events(client.post(url,headers=auth_headers,json={
        "content":"从所选账户向所选联系人模拟转账 1 元，请先准备待确认操作",
        "references":[{"kind":"account","id":account_id},{"kind":"contact","id":contact_id}]
    }))
    assert [e["type"] for e in events]==["action_required","done"]
    assert events[0]["action"]["status"]=="pending"
    with Session(get_engine()) as db:
        assert db.get(Account,account_id).balance_fen==original_balance
        transfers=db.exec(select(TransferRequest)).all()
        assert len(transfers)==1
        assert transfers[0].status=="pending"
        assert transfers[0].recipient_name==contact_name


def test_selected_contact_does_not_authorize_unrequested_transfer(client, auth_headers, monkeypatch):
    from app.models import Contact, TransferRequest
    with Session(get_engine()) as db:
        account_id=db.exec(select(Account)).first().id
        contact_id=db.exec(select(Contact)).first().id
    class FakeLLM:
        async def stream(self,messages,tools=None):
            yield LLMChunk(tool_calls=[{"id":"call_safeunused","type":"function",
                "function":{"name":"prepare_transfer","arguments":json.dumps({
                    "source_token":"fake_source", "recipient_contact_token":"fake_contact",
                    "recipient_name":"wrong_receiver", "amount_fen":100
                })}}])
    monkeypatch.setattr("app.agent.loop.get_llm",FakeLLM)
    cid=_conversation(client,auth_headers)
    events=_events(client.post(f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,json={"content":"请查看这个账户和联系人",
            "references":[{"kind":"account","id":account_id},{"kind":"contact","id":contact_id}]}))
    assert not any(e["type"]=="action_required" for e in events)
    with Session(get_engine()) as db:
        assert not db.exec(select(TransferRequest)).all()
