"""Explicitly selected owned account is server-bound for a prepared transfer."""
import json
import re
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, TransferRequest, User


@pytest.fixture(autouse=True)
def normal_risk_time(monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)


def _events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


@pytest.mark.parametrize("model_source", [None, "fabricated-opaque-token"])
def test_selected_account_rebinds_source_even_with_phone_recipient(
    client, auth_headers, monkeypatch, model_source,
):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        first = session.exec(select(Account).where(Account.user_id == user.id)).first()
        session.add(Account(
            user_id=user.id, name="备用账户", masked_number="**** 7777",
            balance_fen=500_000, currency="CNY",
        ))
        session.commit()
        selected_id = first.id

    class Model:
        async def stream(self, messages, tools=None):
            phone = re.search(r"<PHONE_TMP_[^>]+>", messages[-1]["content"])
            assert phone is not None
            arguments = {
                "recipient_name": "模拟收款人",
                "amount_fen": 100,
                "target_token": phone.group(),
            }
            if model_source:
                arguments["source_token"] = model_source
            yield LLMChunk(tool_calls=[{
                "id": "call_legal", "type": "function",
                "function": {"name": "prepare_transfer",
                             "arguments": json.dumps(arguments)},
            }])

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    conversation = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    response = client.post(
        f"/api/chat/conversations/{conversation}/messages",
        json={"content": "用所选账户给模拟收款人 13812345678 转账1元",
              "references": [{"kind": "account", "id": selected_id}]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    actions = [event for event in _events(response) if event["type"] == "action_required"]
    assert len(actions) == 1
    assert actions[0]["action"]["risk_level"] == "yellow"
    with Session(get_engine()) as session:
        record = session.get(TransferRequest, actions[0]["transfer_id"])
        assert record.account_id == selected_id
        assert record.amount_fen == 100
        assert session.get(Account, selected_id).balance_fen == 500_000


def test_two_accounts_without_explicit_selection_still_cannot_prepare(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        session.add(Account(
            user_id=user.id, name="备用账户", masked_number="**** 7777",
            balance_fen=500_000, currency="CNY",
        ))
        session.commit()

    class Model:
        async def stream(self, messages, tools=None):
            phone = re.search(r"<PHONE_TMP_[^>]+>", messages[-1]["content"])
            assert phone
            yield LLMChunk(tool_calls=[{
                "id": "call_unselected", "type": "function",
                "function": {"name": "prepare_transfer", "arguments": json.dumps({
                    "recipient_name": "模拟收款人", "amount_fen": 100,
                    "target_token": phone.group(),
                })},
            }])

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    conversation = client.post("/api/chat/conversations", json={},
                               headers=auth_headers).json()["id"]
    result = client.post(
        f"/api/chat/conversations/{conversation}/messages",
        json={"content": "向模拟收款人 13812345678 转账1元"},
        headers=auth_headers,
    )
    assert result.status_code == 200
    assert not any(event["type"] == "action_required" for event in _events(result))
    with Session(get_engine()) as session:
        assert session.exec(select(TransferRequest)).all() == []


def test_sensitive_number_in_recipient_name_fails_closed_with_actionable_feedback(
    client, auth_headers, monkeypatch,
):
    from app.tools.transfer_tools import TransferArguments

    schema = TransferArguments.model_json_schema()["properties"]
    assert "手机号" in schema["recipient_name"]["description"]
    assert "target_token" in schema["recipient_name"]["description"]

    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        account = session.exec(select(Account).where(Account.user_id == user.id)).one()

    class Model:
        attempts = 0
        feedback = ""

        async def stream(self, messages, tools=None):
            self.attempts += 1
            if self.attempts == 1:
                phone = re.search(r"<PHONE_TMP_[^>]+>", messages[-1]["content"])
                assert phone
                yield LLMChunk(tool_calls=[{
                    "id": "unsafe_first", "type": "function",
                    "function": {"name": "prepare_transfer", "arguments": json.dumps({
                        "recipient_name": "模拟收款人 13812345678",
                        "target_token": phone.group(), "amount_fen": 100,
                    })},
                }])
            else:
                replies = [m["content"] for m in messages if m["role"] == "tool"]
                self.feedback = " ".join(replies)
                yield LLMChunk(content="请核对收款人姓名。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    conversation = client.post("/api/chat/conversations", json={},
                               headers=auth_headers).json()["id"]
    response = client.post(
        f"/api/chat/conversations/{conversation}/messages",
        json={"content": "从已选账户给模拟收款人 13812345678 转账1元",
              "references": [{"kind": "account", "id": account.id}]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert not any(e["type"] == "action_required" for e in _events(response))
    assert "收款人姓名不能包含手机号" in model.feedback
    assert "13812345678" not in model.feedback
    with Session(get_engine()) as session:
        assert session.exec(select(TransferRequest)).all() == []
        assert session.get(Account, account.id).balance_fen == 500_000
