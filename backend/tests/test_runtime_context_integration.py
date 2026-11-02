"""Runtime wiring tests: model-visible context and safe no-Tool conversations."""
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Card


def _events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_context_is_compiled_once_with_verified_object_and_prior_history(
    client, auth_headers, monkeypatch,
):
    class CaptureModel:
        calls = []

        async def stream(self, messages, tools=None):
            self.calls.append([dict(item) for item in messages])
            yield LLMChunk(content="您好，需要什么帮助？")

    llm = CaptureModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)

    conversation_id = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    endpoint = f"/api/chat/conversations/{conversation_id}/messages"
    assert _events(client.post(
        endpoint, json={"content": "你好"}, headers=auth_headers,
    ))[-1]["type"] == "done"

    with Session(get_engine()) as session:
        card, account = session.exec(
            select(Card, Account).join(Account, Card.account_id == Account.id)
        ).first()

    request = "请查询这张卡片的状态"
    response = client.post(
        endpoint, json={
            "content": request,
            "references": [{"kind": "card", "id": card.id}],
        }, headers=auth_headers,
    )
    assert _events(response)[-1]["type"] == "done"
    assert len(llm.calls) == 2
    second_call = llm.calls[-1]
    assert [item["role"] for item in second_call] == [
        "system", "user", "assistant", "user",
    ]
    current = second_call[-1]["content"]
    assert current.startswith(request)
    assert current.count(request) == 1
    assert current.count("[以下是服务端验证的金融对象") == 1
    assert current.count("card_id=") == 1
    assert second_call[1]["content"] == "你好"
    assert all(
        "以下是服务端验证的金融对象" not in item["content"]
        for item in second_call[:-1]
    )


def test_safe_clarification_is_not_replaced_by_fixed_script(
    client, auth_headers, monkeypatch,
):
    class ClarifyingModel:
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="请问您想从哪个账户转账，金额是多少？")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: ClarifyingModel())
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "我想转账"}, headers=auth_headers,
    ))
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["content"] == "请问您想从哪个账户转账，金额是多少？"
    assert all(e["type"] not in {"action_required", "operation_result"} for e in events)


def test_natural_prefixed_clarification_avoids_second_model_call(
    client, auth_headers, monkeypatch,
):
    class PrefixedQuestionModel:
        mode = "openai"
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            assert self.calls == 1, "Valid safe clarification should skip Recovery"
            yield LLMChunk(content="可以的。请问你想从哪个账户转账？")

    model = PrefixedQuestionModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "我想转账"}, headers=auth_headers,
    ))
    assert model.calls == 1
    assert [e["type"] for e in events] == ["delta", "done"]
    assert events[-1]["message"]["content"] == "可以的。请问你想从哪个账户转账？"


def test_missing_transfer_details_are_asked_by_the_model(
    client, auth_headers, monkeypatch,
):
    class ClarifyingModel:
        mode = "openai"
        calls = []

        async def stream(self, messages, tools=None):
            self.calls.append((messages, tools))
            yield LLMChunk(content="请问您想从哪个账户转账，金额是多少？")

    model = ClarifyingModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "我想转账"}, headers=auth_headers,
    ))
    assert len(model.calls) == 1
    text = events[-1]["message"]["content"]
    assert text == "请问您想从哪个账户转账，金额是多少？"
    assert all(event["type"] != "action_required" for event in events)
