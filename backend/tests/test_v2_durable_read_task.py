"""An unfinished READ goal survives a turn and resumes only with a new verified account."""
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.db.session import get_engine
from app.models import Account, ConversationTask
from app.services.conversation_tasks import (
    ReadGoal, can_resume_task, classify_pending_read_goal,
)


def _events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_pending_goal_classifier_does_not_capture_operations():
    assert classify_pending_read_goal("帮我分析2026年1月的收支") == ReadGoal(
        kind="bill_analysis", month="2026-01",
    )
    assert classify_pending_read_goal("帮我转账100元，再查账单") is None
    assert classify_pending_read_goal("解释什么是账单") is None
    assert can_resume_task("继续")
    assert not can_resume_task("转账200元")
    assert not can_resume_task("介绍复利")


def test_missing_account_read_task_resumes_from_persisted_state(
    client, auth_headers, monkeypatch,
):
    monkeypatch.setattr(settings, "generative_ui_enabled", False)
    requests = []

    class Model:
        mode = "openai"
        async def stream(self, messages, tools=None):
            requests.append({"messages": messages, "tools": tools})
            if tools is None:
                if '"expected"' in messages[-1]["content"]:
                    yield LLMChunk(content=json.dumps({
                        "question": "请问需要查询哪个账户的账单？",
                    }, ensure_ascii=False))
                else:
                    yield LLMChunk(content=json.dumps({
                        "narrative": "已经获得本次可信账单，可以关注收支分类的构成；仅凭单月数据无法判断变化的原因。",
                    }, ensure_ascii=False))
                return
            if any(item.get("role") == "tool" for item in messages):
                yield LLMChunk(content="请查看可信账单结果。")
            elif "服务端保存的未完成只读目标" in messages[-1]["content"]:
                yield LLMChunk(tool_calls=[{
                    "id": "call_pending_bill_v2", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'},
                }])
            else:
                yield LLMChunk(content="请问需要查询哪个账户的账单？")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    cid = client.post("/api/chat/conversations", headers=auth_headers,
                      json={}).json()["id"]
    url = f"/api/chat/conversations/{cid}/messages"
    first = _events(client.post(url, headers=auth_headers,
                                json={"content": "帮我分析2026-01的账单与收支"}))
    assert first[-1]["type"] == "done"
    with Session(get_engine()) as session:
        pending = session.get(ConversationTask, cid)
        assert pending is not None
        assert pending.status == "needs_account"
        assert pending.kind == "bill_analysis"
        assert pending.month == "2026-01"
        account_id = session.exec(select(Account)).first().id

    second = _events(client.post(url, headers=auth_headers, json={
        "content": "继续",
        "references": [{"kind": "account", "id": account_id}],
    }))
    assert second[-1]["type"] == "done"
    assert any(event["type"] == "bill_result" for event in second)
    assert any("服务端保存的未完成只读目标" in str(m["content"])
               for call in requests if call["tools"] is not None
               for m in call["messages"] if m["role"] == "user")

    with Session(get_engine()) as session:
        completed = session.get(ConversationTask, cid)
        assert completed.status == "completed"

    count = len(requests)
    third = _events(client.post(url, headers=auth_headers,
                                json={"content": "你好"}))
    assert third[-1]["type"] == "done"
    assert all("服务端保存的未完成只读目标" not in str(m["content"])
               for call in requests[count:] for m in call["messages"])
