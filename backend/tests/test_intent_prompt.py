import json
import re

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, Card, Contact


def _ids():
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).first()
        contact = session.exec(select(Contact).where(Contact.name == "张三")).one()
        return account.id, contact.id


def _conversation(client, headers):
    return client.post("/api/chat/conversations", json={}, headers=headers).json()["id"]


def test_drag_intent_is_rendered_as_tokenized_prompt(client, auth_headers, monkeypatch):
    account_id, contact_id = _ids()
    seen = {}

    class FakeLLM:
        async def stream(self, messages, tools=None):
            seen["messages"] = messages
            yield LLMChunk(content="请补充金额。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"
    response = client.post(url, headers=auth_headers, json={
        "content": "1000 元，饭钱",
        "intent": {
            "action": "transfer",
            "source": {"kind": "account", "id": account_id},
            "target": {"kind": "contact", "id": contact_id},
        },
    })
    assert response.status_code == 200
    prompt = seen["messages"][-1]["content"]
    assert prompt.startswith("【前置意图】")
    assert "1000 元，饭钱" in prompt
    assert re.search(r"<CARD_[A-Za-z]{32}>", prompt)
    assert re.search(r"<CONTACT_[A-Za-z]{32}>", prompt)
    assert "张三" in prompt
    assert "**** 0001" not in prompt

    history = client.get(url, headers=auth_headers).json()
    assert history[0]["content"].startswith("【前置意图】转账 · 演示活期账户 → 张三")
    assert "1000 元，饭钱" in history[0]["content"]
    assert "<CARD_" not in json.dumps(history, ensure_ascii=False)
    assert "<CONTACT_" not in json.dumps(history, ensure_ascii=False)


def test_intent_rejects_cross_user_and_undefined_combinations(client, auth_headers):
    account_id, contact_id = _ids()
    conversation_id = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"

    bad = client.post(url, headers=auth_headers, json={
        "content": "试试",
        "intent": {
            "action": "redeem",
            "source": {"kind": "account", "id": account_id},
            "target": {"kind": "contact", "id": contact_id},
        },
    })
    assert bad.status_code == 400

    same = client.post(url, headers=auth_headers, json={
        "content": "试试",
        "intent": {
            "action": "internal_transfer",
            "source": {"kind": "account", "id": account_id},
            "target": {"kind": "account", "id": account_id},
        },
    })
    assert same.status_code == 422

    with Session(get_engine()) as session:
        foreign = session.exec(select(Contact).where(Contact.id != contact_id)).first()
    # A valid local contact is not enough if the account is replaced by a foreign ID.
    foreign_intent = client.post(url, headers=auth_headers, json={
        "content": "试试",
        "intent": {
            "action": "transfer",
            "source": {"kind": "account", "id": 99999},
            "target": {"kind": "contact", "id": foreign.id},
        },
    })
    assert foreign_intent.status_code == 400


def test_internal_transfer_intent_prompt_tokens_drive_green_execution(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        source = session.exec(select(Account)).first()
        target = Account(user_id=source.user_id, name="第二账户", masked_number="**** 0099",
                         balance_fen=200_000)
        session.add(target)
        session.flush()
        session.add(Card(account_id=target.id))
        session.commit()
        source_id, target_id = source.id, target.id

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                tokens = re.findall(r"<(?:CARD|CONTACT|PRODUCT)_[A-Za-z]{32}>", messages[-1]["content"])
                assert len(tokens) == 2
                yield LLMChunk(tool_calls=[{
                    "id": "internal-1", "type": "function",
                    "function": {"name": "prepare_internal_transfer", "arguments": json.dumps({
                        "source_token": tokens[0], "target_token": tokens[1],
                        "amount_fen": 50_000, "note": "内部",
                    })},
                }])
            else:
                yield LLMChunk(content="内部转账已完成。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           headers=auth_headers, json={
        "content": "500 元",
        "intent": {
            "action": "internal_transfer",
            "source": {"kind": "account", "id": source_id},
            "target": {"kind": "account", "id": target_id},
        },
    })
    assert response.status_code == 200
    assert '"type": "operation_result"' in response.text
    with Session(get_engine()) as session:
        assert session.get(Account, source_id).balance_fen == 450_000
        assert session.get(Account, target_id).balance_fen == 250_000


def test_intent_rejects_model_amount_mismatch(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        source = session.exec(select(Account)).first()
        target = Account(user_id=source.user_id, name="第二账户", masked_number="**** 0099",
                         balance_fen=200_000)
        session.add(target)
        session.flush()
        session.add(Card(account_id=target.id))
        session.commit()
        source_id, target_id = source.id, target.id

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                tokens = re.findall(r"<(?:CARD|CONTACT|PRODUCT)_[A-Za-z]{32}>", messages[-1]["content"])
                yield LLMChunk(tool_calls=[{
                    "id": "wrong-amount", "type": "function",
                    "function": {"name": "prepare_internal_transfer", "arguments": json.dumps({
                        "source_token": tokens[0], "target_token": tokens[1],
                        "amount_fen": 99_900, "note": "",
                    })},
                }])
            else:
                yield LLMChunk(content="金额不一致，未执行。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           headers=auth_headers, json={
        "content": "500 元",
        "intent": {
            "action": "internal_transfer",
            "source": {"kind": "account", "id": source_id},
            "target": {"kind": "account", "id": target_id},
        },
    })
    assert response.status_code == 200
    assert "operation_result" not in response.text
    with Session(get_engine()) as session:
        assert session.get(Account, source_id).balance_fen == 500_000
        assert session.get(Account, target_id).balance_fen == 200_000

def test_second_internal_transfer_turn_creates_yellow_action(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        source = session.exec(select(Account)).first()
        target = Account(user_id=source.user_id, name="第二账户", masked_number="**** 0099",
                         balance_fen=300_000)
        session.add(target)
        session.flush()
        session.add(Card(account_id=target.id))
        session.commit()
        source_id, target_id = source.id, target.id

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls % 2 == 1:
                content = messages[-1]["content"]
                tokens = re.findall(r"<CARD_[A-Za-z]{32}>", content)
                amount = int(re.search(r"(\d+) 元", content).group(1)) * 100
                yield LLMChunk(tool_calls=[{
                    "id": f"internal-{self.calls}", "type": "function",
                    "function": {"name": "prepare_internal_transfer", "arguments": json.dumps({
                        "source_token": tokens[0], "target_token": tokens[1],
                        "amount_fen": amount, "note": "",
                    })},
                }])
            else:
                yield LLMChunk(content="处理完成。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"

    first = client.post(url, headers=auth_headers, json={
        "content": "500 元",
        "intent": {"action": "internal_transfer",
                   "source": {"kind": "account", "id": target_id},
                   "target": {"kind": "account", "id": source_id}},
    })
    assert first.status_code == 200
    assert '"type": "operation_result"' in first.text

    second = client.post(url, headers=auth_headers, json={
        "content": "1200 元",
        "intent": {"action": "internal_transfer",
                   "source": {"kind": "account", "id": source_id},
                   "target": {"kind": "account", "id": target_id}},
    })
    assert second.status_code == 200
    assert '"type": "action_required"' in second.text
    assert '"risk_level": "yellow"' in second.text
    assert "请先选择付款账户与收款联系人" not in second.text

# Separate regression: a successful green internal transfer must not leave a
# misleading "tool unavailable" summary in the assistant message.
def test_green_internal_transfer_summary_is_not_tool_unavailable(client, auth_headers, monkeypatch):
    with Session(get_engine()) as session:
        source = session.exec(select(Account)).first()
        target = Account(user_id=source.user_id, name="第二账户", masked_number="**** 0099",
                         balance_fen=200_000)
        session.add(target)
        session.flush()
        session.add(Card(account_id=target.id))
        session.commit()
        source_id, target_id = source.id, target.id

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                tokens = re.findall(r"<CARD_[A-Za-z]{32}>", messages[-1]["content"])
                yield LLMChunk(tool_calls=[{
                    "id": "summary-1", "type": "function",
                    "function": {"name": "prepare_internal_transfer", "arguments": json.dumps({
                        "source_token": tokens[0], "target_token": tokens[1],
                        "amount_fen": 50_000, "note": "",
                    })},
                }])
            else:
                yield LLMChunk(content="处理完成。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages",
                           headers=auth_headers, json={
        "content": "500 元",
        "intent": {"action": "internal_transfer",
                   "source": {"kind": "account", "id": source_id},
                   "target": {"kind": "account", "id": target_id}},
    })
    assert response.status_code == 200
    assert "工具不可用" not in response.text
    assert "内部转账已完成" in response.text
