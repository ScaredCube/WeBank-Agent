"""Server-controlled amount verification for typed finance references."""
import json

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Contact, TransferRequest
from app.risk.transfer_intent import requested_transfer_amount_fen


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

    class NeverCallModel:
        async def stream(self, messages, tools=None):
            raise AssertionError("Model must not be invoked for ambiguous transfer amount")
            yield LLMChunk(content="invalid")  # pragma: no cover

    monkeypatch.setattr("app.agent.loop.get_llm", NeverCallModel)
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
