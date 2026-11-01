"""Idempotent Agent POST across retries, including pending financial actions."""
import json
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import Account, ChatSubmission, Contact, TransferRequest, User
from app.services.chat_submissions import claim_submission, fingerprint


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def cid(client, headers):
    response = client.post("/api/chat/conversations", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def url(cid):
    return f"/api/chat/conversations/{cid}/messages"


def test_readonly_duplicate_returns_saved_result_without_reexecution(client, auth_headers, monkeypatch):
    with Session(get_engine()) as db:
        aid = db.exec(select(Account)).first().id
    class BillLLM:
        calls = 0
        async def stream(self,messages,tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id":"call_oneread","type":"function",
                    "function":{"name":"get_monthly_bill","arguments":'{"month":"2026-01"}'}}])
            else:
                raise AssertionError("The completed read-only request must not execute model again")
    fake = BillLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: fake)
    conversation_id=cid(client,auth_headers)
    payload={"content":"查询此账户 2026-01 账单",
             "references":[{"kind":"account","id":aid}],
             "request_id":"req-test-bill-001"}
    first=events(client.post(url(conversation_id),headers=auth_headers,json=payload))
    again=events(client.post(url(conversation_id),headers=auth_headers,json=payload))
    assert [event["type"] for event in first] == ["bill_result","delta","done"]
    assert [event["type"] for event in again] == ["done"]
    assert first[-1]["message"]["id"] == again[-1]["message"]["id"]
    assert fake.calls == 1
    history=client.get(url(conversation_id),headers=auth_headers).json()
    assert [item["role"] for item in history]==["user","assistant"]
    status=client.get(f"/api/chat/conversations/{conversation_id}/requests/req-test-bill-001",
                      headers=auth_headers)
    assert status.status_code==200
    assert status.headers["cache-control"]=="no-store"
    assert status.json()["state"]=="completed"
    assert status.json()["message"]["id"]==first[-1]["message"]["id"]
    assert "<CARD_" not in str(status.json())
    with Session(get_engine()) as db:
        attempts=db.exec(select(ChatSubmission)).all()
        assert len(attempts)==1 and attempts[0].user_message_id==history[0]["id"]


def test_duplicate_pending_transfer_never_reissues_token_or_prepares_again(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as db:
        aid=db.exec(select(Account)).first().id
        contact_id=db.exec(select(Contact)).first().id
        original=db.get(Account,aid).balance_fen

    class PrepareLLM:
        calls=0
        async def stream(self,messages,tools=None):
            self.calls+=1
            yield LLMChunk(tool_calls=[{"id":"call_safecreate","type":"function",
                "function":{"name":"prepare_transfer","arguments":json.dumps({
                    "amount_fen":100,"source_token":"wrong","recipient_contact_token":"wrong",
                    "recipient_name":"wrong"
                })}}])
    fake=PrepareLLM()
    monkeypatch.setattr("app.agent.loop.get_llm",lambda:fake)
    conv=cid(client,auth_headers)
    payload={"content":"从所选账户向所选联系人模拟转账 1 元，先生成待确认操作供我核对",
             "references":[{"kind":"account","id":aid},{"kind":"contact","id":contact_id}],
             "request_id":"req-test-transfer-001"}
    first=events(client.post(url(conv),headers=auth_headers,json=payload))
    action=next(e for e in first if e["type"]=="action_required")
    assert action["confirmation_token"]
    retry=events(client.post(url(conv),headers=auth_headers,json=payload))
    assert [e["type"] for e in retry]==["action_warning","done"]
    assert "confirmation_token" not in json.dumps(retry)
    assert "action_required" not in [e["type"] for e in retry]
    assert fake.calls==1
    status=client.get(f"/api/chat/conversations/{conv}/requests/{payload['request_id']}",
                      headers=auth_headers).json()
    assert status["state"]=="action_pending"
    assert status["pending_action_id"]==action["action"]["id"]
    assert "confirmation_token" not in json.dumps(status)
    with Session(get_engine()) as db:
        pending=db.exec(select(TransferRequest)).all()
        assert len(pending)==1 and pending[0].status=="pending"
        assert db.get(Account,aid).balance_fen==original
    assert [m["role"] for m in client.get(url(conv),headers=auth_headers).json()]==["user"]


def test_conflicting_payload_or_conversation_cannot_reuse_key(client,auth_headers,monkeypatch):
    class EchoModel:
        calls=0
        async def stream(self,messages,tools=None):
            self.calls+=1
            yield LLMChunk(content="收到")
    model=EchoModel()
    monkeypatch.setattr("app.agent.loop.get_llm",lambda:model)
    conv=cid(client,auth_headers)
    payload={"content":"你好","request_id":"req-conflict-123"}
    assert events(client.post(url(conv),headers=auth_headers,json=payload))[-1]["type"]=="done"
    assert client.post(url(conv),headers=auth_headers,json={
        "content":"另一条消息","request_id":payload["request_id"]}).status_code==409
    another=cid(client,auth_headers)
    assert client.post(url(another),headers=auth_headers,json=payload).status_code==409
    assert model.calls==1
    assert client.get(url(another),headers=auth_headers).json()==[]


def test_status_is_user_and_conversation_isolated(client,auth_headers,monkeypatch):
    class EchoModel:
        async def stream(self,messages,tools=None):
            yield LLMChunk(content="已收到")
    monkeypatch.setattr("app.agent.loop.get_llm",EchoModel)
    conv=cid(client,auth_headers)
    payload={"content":"你好","request_id":"req-isolated-456"}
    events(client.post(url(conv),headers=auth_headers,json=payload))
    with Session(get_engine()) as db:
        foreign=User(username="isolated_retry_user",password_hash="test",display_name="other")
        db.add(foreign);db.commit();db.refresh(foreign)
        foreign_id=foreign.id
    foreign_headers={"Authorization":"Bearer "+create_access_token(str(foreign_id))}
    endpoint=f"/api/chat/conversations/{conv}/requests/{payload['request_id']}"
    assert client.get(endpoint,headers=foreign_headers).status_code==404
    assert client.get(endpoint).status_code==401
    own_other=cid(client,auth_headers)
    assert client.get(f"/api/chat/conversations/{own_other}/requests/{payload['request_id']}",
                      headers=auth_headers).status_code==404
    # Another user may reuse the same opaque request ID in their OWN conversation.
    other=cid(client,foreign_headers)
    result=events(client.post(url(other),headers=foreign_headers,json=payload))
    assert result[-1]["type"]=="done"


def test_database_unique_constraint_prevents_duplicate_claims(client,auth_headers):
    with Session(get_engine()) as db:
        user=db.exec(select(User)).first()
        user_id=user.id
    conv=cid(client,auth_headers)
    digest=fingerprint("same text",[])
    def claim():
        with Session(get_engine()) as db:
            value,fresh=claim_submission(db,user_id=user_id,conversation_id=conv,
                                         request_id="req-atomic-test-01",payload_digest=digest)
            return value.id,fresh
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:claim(),range(2)))
    assert sorted(fresh for _,fresh in results)==[False,True]
    assert results[0][0]==results[1][0]

def test_inflight_and_interrupted_requests_fail_closed_without_reexecution(
    client, auth_headers, monkeypatch,
):
    from app.services.chat_submissions import advance_submission

    class NeverRunModel:
        async def stream(self, messages, tools=None):
            raise AssertionError("Concurrent duplicate must not reach model")
            yield LLMChunk(content="unreachable")  # pragma: no cover

    monkeypatch.setattr("app.agent.loop.get_llm", NeverRunModel)
    conv=cid(client,auth_headers)
    reqid="req-inflight-accepted"
    with Session(get_engine()) as db:
        user=db.exec(select(User)).first()
        pending, fresh = claim_submission(
            db,user_id=user.id,conversation_id=conv,request_id=reqid,
            payload_digest=fingerprint("prepare pending",[]),
        )
        assert fresh
        submission_id=pending.id
    payload={"content":"prepare pending","request_id":reqid}
    assert client.post(url(conv),headers=auth_headers,json=payload).status_code==409
    status=client.get(f"/api/chat/conversations/{conv}/requests/{reqid}",
                      headers=auth_headers).json()
    assert status["state"]=="processing" and status["user_message_id"] is None

    advance_submission(submission_id=submission_id,state="interrupted")
    assert client.post(url(conv),headers=auth_headers,json=payload).status_code==409
    status=client.get(f"/api/chat/conversations/{conv}/requests/{reqid}",
                      headers=auth_headers).json()
    assert status["state"]=="interrupted"
    assert client.get(url(conv),headers=auth_headers).json()==[]


def test_fingerprint_is_keyed_and_references_are_canonical(client):
    from types import SimpleNamespace
    first=[SimpleNamespace(kind="contact",id=2),SimpleNamespace(kind="account",id=1)]
    second=list(reversed(first))
    one=fingerprint("转账 1 元",first)
    two=fingerprint("转账 1 元",second)
    assert one==two and len(one)==64
    assert one!=fingerprint("转账 2 元",first)
    assert one!=__import__("hashlib").sha256(__import__("json").dumps({
        "content":"转账 1 元","references":[("account",1),("contact",2)]
    },sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
