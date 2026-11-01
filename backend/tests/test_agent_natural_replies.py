"""Verify conversational output without regressing grounded bank Tool safety."""
import json

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.agent.prompts import SYSTEM_PROMPT, GUARD_SYSTEM_PROMPT
from app.agent.response_policy import tool_free_reply
from app.db.session import get_engine
from app.models import Account, Message, TransferRequest


def _events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _chat(client, headers, text, *, conversation=None):
    if conversation is None:
        start = client.post("/api/chat/conversations", headers=headers, json={})
        assert start.status_code == 201
        conversation = start.json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=headers, json={"content": text})
    return conversation, _events(response)


def test_system_prompt_is_precise_without_weakening_guard():
    assert "小We" in SYSTEM_PROMPT
    assert "不要把没有调用工具等同于失败" in SYSTEM_PROMPT
    assert "recipient_contact_token" in SYSTEM_PROMPT
    assert "服务端" in SYSTEM_PROMPT and "账户" in SYSTEM_PROMPT
    assert "无法判断、信息不足" in GUARD_SYSTEM_PROMPT


class ConversationalProvider:
    mode = "openai"
    model = "deterministic-test"

    def __init__(self):
        self.history_seen = []

    async def stream(self, messages, tools=None):
        self.history_seen.append([m.copy() for m in messages])
        last = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if last == "hi":
            yield LLMChunk(content="你好，我是小We。")
        elif last == "我想转账":
            yield LLMChunk(content="可以的。请先选择付款账户和收款联系人，告诉我金额；我会先准备一笔待确认操作。")
        else:
            yield LLMChunk(content="请告诉我你需要哪项帮助。")
        yield LLMChunk(finish_reason="stop")


def test_freeform_greeting_and_transfer_clarification_persist(
    client, auth_headers, monkeypatch,
):
    model = ConversationalProvider()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    conversation, first = _chat(client, auth_headers, "hi")
    assert first[-1]["message"]["content"] == "你好，我是小We。"
    assert first[0]["type"] == "delta"
    conversation, second = _chat(client, auth_headers, "我想转账", conversation=conversation)
    text = second[-1]["message"]["content"]
    assert "选择付款账户" in text
    assert "未能通过工具完成查询" not in text
    assert len(model.history_seen) == 2
    assert any(m["content"] == "hi" for m in model.history_seen[1])
    fetched = client.get(f"/api/chat/conversations/{conversation}/messages",
                         headers=auth_headers).json()
    assert [m["role"] for m in fetched] == ["user", "assistant", "user", "assistant"]
    assert fetched[-1]["content"] == text
    with Session(get_engine()) as db:
        assert not db.exec(select(TransferRequest)).all()
        assert db.exec(select(Account)).one().balance_fen == 500000


@pytest.mark.parametrize(("raw", "blocked"), [
    ("您的余额是999999元。", "999999"),
    ("您这个月账单共计两万元。", "两万元"),
    ("你的余额有一百万，转账已经成功。", "一百万"),
    ("我已经替你转账成功了。", "转账成功"),
    ("我刚刚帮你挂失了银行卡。", "帮你挂失"),
    ("服务端显示您的交易明细已更新。", "交易明细"),
    ("内部参考：recipient_contact_token=secret", "secret"),
    ("已查到您的账户信息。", "已查到"),
])
def test_unverified_bank_claims_do_not_leave_model_buffer(raw, blocked):
    safe = tool_free_reply(raw)
    assert safe != raw
    assert blocked not in safe


def test_no_tool_model_cannot_invent_balance_or_transfer(
    client, auth_headers, monkeypatch,
):
    class HallucinatingModel:
        mode = "openai"
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="您的余额是999999元，我刚刚帮您完成了转账。")
            yield LLMChunk(finish_reason="stop")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: HallucinatingModel())
    _, events = _chat(client, auth_headers, "余额是多少？")
    answer = events[-1]["message"]["content"]
    assert "999999" not in answer
    assert "完成了转账" not in answer
    assert "还没有查到" in answer or "尚未完成" in answer
    with Session(get_engine()) as db:
        assert not db.exec(select(TransferRequest)).all()


def test_empty_or_overlong_untrusted_text_falls_back():
    assert "告诉我" in tool_free_reply("")
    assert "告诉我" in tool_free_reply("无害" * 3000)


def test_numbers_are_not_exposed_as_verified_bank_data():
    assert "1234" not in tool_free_reply("已查询到账户余额是1234元。")
    assert tool_free_reply("你好，我可以帮你了解银行服务。").startswith("你好")
