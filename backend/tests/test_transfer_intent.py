"""Server-controlled amount verification for typed finance references."""
import json

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Contact, TransferRequest
from app.risk.transfer_intent import (
    requested_intent_amount_fen, requested_transfer_amount_fen,
)


@pytest.mark.parametrize(("text", "amount"), [
    ("从我的账户转账 1 元", 100),
    ("请给小张汇款 12.30 元", 1230),
    ("模拟打款 0.01元", 1),
    ("转账 2角", 20),
    ("转账 15分", 15),
    ("转账 1.1 元", 110),
    ("转账 0 元", None),
    ("转账 1.001 元", None),
    ("转账 1元和2元", None),
    ("转账 1.5分", None),
    ("想给联系人转账", None),
    ("给联系人准备 1 元", None),
    ("查询余额 10元", None),
    ("转账 -1元", None),
    ("转账 - 1元", None),
    ("转账 −1 元", None),
    ("我不想转账 1 元", None),
    ("请不要转账 1 元", None),
    ("先不要给这个人转账 1 元", None),
    ("取消转账 1 元", None),
])
def test_conservative_transfer_amount_extraction(text, amount):
    assert requested_transfer_amount_fen(text) == amount


@pytest.mark.parametrize(("request_text","model_amount"), [
    ("从所选账户向所选联系人模拟转账 1 元，请核对", 1000),
    ("请查看所选账户和联系人", 100),
    ("准备向所选联系人转账 1 元和 2 元", 100),
    ("从所选账户向所选联系人模拟转账 1.001 元", 100),
    ("我不想从这个账户向这个联系人转账 1 元", 100),
])
def test_model_cannot_substitute_or_guess_amount(client, auth_headers, monkeypatch,
                                                 request_text, model_amount):
    with Session(get_engine()) as db:
        account=db.exec(select(Account)).first()
        contact=db.exec(select(Contact)).first()
        assert account and contact
        account_id, contact_id, original=account.id, contact.id, account.balance_fen

    class BadAmountLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[{
                "id": "call_safefixed", "type": "function",
                "function": {"name": "prepare_transfer", "arguments": json.dumps({
                    "amount_fen": model_amount,
                    "recipient_name": "untrusted_model_name",
                    "source_token": "wrong_source",
                    "recipient_contact_token": "wrong_contact",
                }, ensure_ascii=False)},
            }])

    monkeypatch.setattr("app.agent.loop.get_llm", BadAmountLLM)
    cid=client.post("/api/chat/conversations",headers=auth_headers,json={}).json()["id"]
    response=client.post(f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,json={
            "content": request_text,
            "references":[{"kind":"account","id":account_id},
                          {"kind":"contact","id":contact_id}],
        })
    assert response.status_code==200
    events=[json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]
    assert not any(event["type"]=="action_required" for event in events)
    with Session(get_engine()) as db:
        assert db.get(Account,account_id).balance_fen==original
        assert not db.exec(select(TransferRequest)).all()

@pytest.mark.parametrize("request_text", [
    "请向这个联系人转账，先让我核对",
    "向这个联系人转账 1 元或者 2 元",
    "向这个联系人转账 -1 元",
])
def test_missing_or_ambiguous_amount_requires_user_clarification(
    client, auth_headers, monkeypatch, request_text,
):
    with Session(get_engine()) as db:
        account_id=db.exec(select(Account)).first().id
        contact_id=db.exec(select(Contact)).first().id

    class AmountModel:
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="请告诉我明确的转账金额。")

    monkeypatch.setattr("app.agent.loop.get_llm", AmountModel)
    conversation=client.post("/api/chat/conversations",headers=auth_headers,json={}).json()["id"]
    url=f"/api/chat/conversations/{conversation}/messages"
    response=client.post(url,headers=auth_headers,json={
        "content":request_text,
        "references":[{"kind":"account","id":account_id},{"kind":"contact","id":contact_id}],
    })
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["type"] for event in events] == ["delta","done"]
    assert "金额" in events[0]["text"]
    assert "金额" in client.get(url,headers=auth_headers).json()[-1]["content"]
    with Session(get_engine()) as db:
        assert db.exec(select(TransferRequest)).all() == []

def test_short_confirmation_reuses_previous_validated_intent(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as db:
        account = db.exec(select(Account)).first()
        contact = db.exec(select(Contact)).first()
        assert account and contact
        account_id, contact_id, original = account.id, contact.id, account.balance_fen

    class ClarifyThenPrepare:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls <= 2:
                yield LLMChunk(content="金额是 500 元吗？")
            elif self.calls == 3:
                assert any(
                    "500.00" in str(message.get("content")) for message in messages
                )
                yield LLMChunk(tool_calls=[{
                    "id": "call_reused_intent", "type": "function",
                    "function": {"name": "prepare_transfer", "arguments": json.dumps({
                        "amount_fen": 50000,
                        "recipient_name": "untrusted",
                        "source_token": "untrusted",
                        "recipient_contact_token": "untrusted",
                    }, ensure_ascii=False)},
                }])
            else:
                yield LLMChunk(content="已准备待确认转账，请在固定弹窗中核对。")

    model = ClarifyThenPrepare()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", headers=auth_headers, json={}).json()["id"]
    url = f"/api/chat/conversations/{cid}/messages"
    first = client.post(url, headers=auth_headers, json={
        "content": "转账金额：500块，还钱",
        "intent": {
            "action": "transfer",
            "source": {"kind": "account", "id": account_id},
            "target": {"kind": "contact", "id": contact_id},
        },
    })
    assert first.status_code == 200
    assert "500 元吗" in first.text

    second = client.post(url, headers=auth_headers, json={"content": "是"})
    assert second.status_code == 200
    events = [json.loads(line[6:]) for line in second.text.splitlines()
              if line.startswith("data: ")]
    action = next(event for event in events if event["type"] == "action_required")
    assert action["action"]["details"]["amount_fen"] == 50000
    assert action["action"]["details"]["recipient_name"] == contact.name
    with Session(get_engine()) as db:
        assert db.get(Account, account_id).balance_fen == original
        transfers = db.exec(select(TransferRequest)).all()
        assert len(transfers) == 1 and transfers[0].status == "pending"

@pytest.mark.parametrize(("text", "amount"), [
    ("转账金额：500块，还钱", 50000),
    ("转账金额：500元，还钱", 50000),
    ("转账金额：500", None),
    ("转账金额：500元或者600元", None),
])
def test_typed_intent_amount_allows_note_after_explicit_unit(text, amount):
    assert requested_intent_amount_fen(text) == amount
