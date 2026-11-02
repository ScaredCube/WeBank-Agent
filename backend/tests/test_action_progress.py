"""Live, scoped action progress is not a replay or an execution mandate."""
import json
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, Contact, PendingAction, User
from app.core.security import create_access_token


@pytest.fixture(autouse=True)
def daytime_policy(monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)


def prepare_from_chat(client, headers, monkeypatch, request_id):
    with Session(get_engine()) as db:
        account_id = db.exec(select(Account)).first().id
        contact_id = db.exec(select(Contact)).first().id

    class OneTool:
        calls = 0
        prepared = False

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.prepared or tools is None:
                yield LLMChunk(content="已生成待确认操作，请在固定弹窗中核对。")
                return
            self.prepared = True
            yield LLMChunk(tool_calls=[{
                "id": "call_progress_1",
                "type": "function",
                "function": {
                    "name": "prepare_transfer",
                    "arguments": json.dumps({
                        "source_token": "untrusted",
                        "recipient_contact_token": "untrusted",
                        "recipient_name": "untrusted",
                        "amount_fen": 100,
                    }),
                },
            }])

    model = OneTool()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    conversation = client.post(
        "/api/chat/conversations", json={}, headers=headers,
    ).json()["id"]
    payload = {
        "content": "从所选账户向所选联系人转账 1 元，先等待我确认",
        "request_id": request_id,
        "references": [
            {"kind": "account", "id": account_id},
            {"kind": "contact", "id": contact_id},
        ],
    }
    response = client.post(
        f"/api/chat/conversations/{conversation}/messages",
        json=payload, headers=headers,
    )
    assert response.status_code == 200
    events = [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    action = next(event for event in events if event["type"] == "action_required")
    assert action["confirmation_token"]
    return conversation, payload, action, model


def get_progress(client, headers, conversation, request_id):
    url = f"/api/chat/conversations/{conversation}/requests/{request_id}"
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()["action_progress"]


def test_request_progress_follows_confirmation_then_execution_without_replay(
    client, auth_headers, monkeypatch,
):
    cid, payload, action, model = prepare_from_chat(
        client, auth_headers, monkeypatch, "req-progress-001",
    )
    action_id = action["action"]["id"]
    progress = get_progress(client, auth_headers, cid, payload["request_id"])
    assert progress == {
        "action_id": action_id,
        "status": "pending",
        "stage": "awaiting_confirmation",
        "execution_state": "not_executed",
    }
    latest = client.get(
        f"/api/chat/conversations/{cid}/action-progress",
        headers=auth_headers,
    )
    assert latest.status_code == 200
    assert latest.headers["cache-control"] == "no-store"
    assert latest.json()["action_progress"] == {
        "request_id": payload["request_id"], **progress,
    }

    confirmed = client.post(
        f"/api/actions/{action_id}/confirm",
        json={"token": action["confirmation_token"]}, headers=auth_headers,
    )
    assert confirmed.status_code == 200
    confirmed_progress = get_progress(
        client, auth_headers, cid, payload["request_id"],
    )
    assert confirmed_progress["stage"] == "awaiting_execution"
    assert confirmed_progress["execution_state"] == "not_executed"

    # Same request ID is still a lookup, never a new Tool invocation.
    repeated = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json=payload, headers=auth_headers,
    )
    assert repeated.status_code == 200
    assert "尚未执行" in repeated.text
    assert action["confirmation_token"] not in repeated.text
    assert model.calls == 1

    executed = client.post(
        f"/api/transfers/{action['transfer_id']}/execute", headers=auth_headers,
    )
    assert executed.status_code == 200
    completed_progress = get_progress(
        client, auth_headers, cid, payload["request_id"],
    )
    assert completed_progress["status"] == "completed"
    assert completed_progress["execution_state"] == "completed"
    repeated = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json=payload, headers=auth_headers,
    )
    assert repeated.status_code == 200
    assert "已记录完成" in repeated.text
    assert action["confirmation_token"] not in repeated.text
    assert model.calls == 1


def test_cancelled_and_expired_actions_remain_readable_without_confirmation_token(
    client, auth_headers, monkeypatch,
):
    cid, payload, action, model = prepare_from_chat(
        client, auth_headers, monkeypatch, "req-progress-cancel",
    )
    action_id = action["action"]["id"]
    cancelled = client.post(
        f"/api/actions/{action_id}/cancel", headers=auth_headers,
    )
    assert cancelled.status_code == 200
    progress = get_progress(client, auth_headers, cid, payload["request_id"])
    assert progress["stage"] == "cancelled"
    assert progress["execution_state"] == "not_executed"

    # A new conversation has no implied permission to read another's progress.
    new_conversation = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    other = client.get(
        f"/api/chat/conversations/{new_conversation}/action-progress",
        headers=auth_headers,
    )
    assert other.json() == {"action_progress": None}
    assert client.get(
        f"/api/chat/conversations/{new_conversation}/requests/{payload['request_id']}",
        headers=auth_headers,
    ).status_code == 404

    with Session(get_engine()) as db:
        pending = db.get(PendingAction, action_id)
        pending.status = "pending"
        pending.expires_at = utcnow() - timedelta(seconds=1)
        db.add(pending)
        db.commit()
    expired = get_progress(client, auth_headers, cid, payload["request_id"])
    assert expired["stage"] == "expired"
    # A previously confirmed action is also unusable once execution expires.
    with Session(get_engine()) as db:
        pending = db.get(PendingAction, action_id)
        pending.status = "confirmed"
        db.add(pending)
        db.commit()
    assert get_progress(client, auth_headers, cid, payload["request_id"])["stage"] == "expired"

    with Session(get_engine()) as db:
        foreign = User(
            username="action_progress_other", password_hash="test",
            display_name="other",
        )
        db.add(foreign)
        db.commit()
        db.refresh(foreign)
        foreign_id = foreign.id
    foreign_headers = {
        "Authorization": "Bearer " + create_access_token(str(foreign_id))
    }
    assert client.get(
        f"/api/chat/conversations/{cid}/action-progress",
        headers=foreign_headers,
    ).status_code == 404
    assert model.calls == 1


def test_agent_can_read_only_latest_verified_action_in_its_conversation(
    client, auth_headers, monkeypatch,
):
    cid, payload, action, _ = prepare_from_chat(
        client, auth_headers, monkeypatch, "req-progress-agent-tool",
    )

    class StatusModel:
        calls = 0
        observation = None

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                assert "get_latest_action_progress" in {
                    item["function"]["name"] for item in tools
                }
                yield LLMChunk(tool_calls=[{
                    "id": "call_progress_status",
                    "type": "function",
                    "function": {
                        "name": "get_latest_action_progress",
                        "arguments": "{}",
                    },
                }])
            else:
                self.observation = json.loads(messages[-1]["content"])
                if self.observation.get("data") is None:
                    yield LLMChunk(content="没有找到可核验的操作状态。")
                else:
                    yield LLMChunk(content="这笔操作尚未执行，请确认状态。")

    model = StatusModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    response = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "刚才转账成功了吗？"}, headers=auth_headers,
    )
    assert response.status_code == 200
    result = [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert model.calls == 2
    assert model.observation["data"]["action_id"] == action["action"]["id"]
    assert model.observation["data"]["execution_state"] == "not_executed"
    assert "确认" in result[-1]["message"]["content"]
    assert "已经成功" not in result[-1]["message"]["content"]
    assert action["confirmation_token"] not in response.text

    # The same authenticated user, but a DIFFERENT conversation.
    other = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    second_model = StatusModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: second_model)
    other_result = client.post(
        f"/api/chat/conversations/{other}/messages",
        json={"content": "刚才那笔转账状态呢？"}, headers=auth_headers,
    )
    assert other_result.status_code == 200
    assert second_model.observation["data"] is None
    assert "没有找到" in other_result.text
    assert action["confirmation_token"] not in other_result.text

def test_action_reply_is_generated_after_execution(client, auth_headers, monkeypatch):
    cid, payload, action, _ = prepare_from_chat(
        client, auth_headers, monkeypatch, "req-action-reply-001",
    )
    confirmed = client.post(
        f"/api/actions/{action['action']['id']}/confirm",
        json={"token": action["confirmation_token"]}, headers=auth_headers,
    )
    assert confirmed.status_code == 200
    executed = client.post(
        f"/api/transfers/{action['transfer_id']}/execute", headers=auth_headers,
    )
    assert executed.status_code == 200

    class ReplyModel:
        async def stream(self, messages, tools=None):
            assert tools is None
            yield LLMChunk(content="转账已完成，金额 1.00 元。")

    monkeypatch.setattr(
        "app.services.action_reply_service.get_llm", lambda: ReplyModel(),
    )
    reply = client.post(
        f"/api/actions/{action['action']['id']}/chat-reply", headers=auth_headers,
    )
    assert reply.status_code == 200
    message = reply.json()["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "转账已完成，金额 1.00 元。"

    history = client.get(
        f"/api/chat/conversations/{cid}/messages", headers=auth_headers,
    ).json()
    assert history[-1]["id"] == message["id"]
    assert history[-1]["content"] == "转账已完成，金额 1.00 元。"
