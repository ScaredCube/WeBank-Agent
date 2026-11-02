"""Pending bill goals only close after their own verified resumed read."""
from datetime import timedelta

from sqlmodel import Session, select

from app.agent.bill_insights import summarize_bill_insights
from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, ConversationTask
from app.core.time import utcnow
from app.services.conversation_tasks import (
    ReadGoal, mark_task_completed, pending_task, remember_pending_task,
)
from tests.test_v2_durable_read_task import _events


def test_task_completion_requires_exact_version_and_target_month(client, auth_headers):
    cid = client.post("/api/chat/conversations", headers=auth_headers,
                      json={}).json()["id"]
    with Session(get_engine()) as db:
        remember_pending_task(db, conversation_id=cid, user_id=1,
                              goal=ReadGoal("bill_analysis", "2026-01"))
        version = db.get(ConversationTask, cid).updated_at
        assert not mark_task_completed(db, conversation_id=cid, user_id=1,
                                       resumed_version=version,
                                       expected_month="2026-01",
                                       verified_months={"2026-02"})
        assert db.get(ConversationTask, cid).status == "needs_account"
        assert not mark_task_completed(db, conversation_id=cid, user_id=1,
                                       resumed_version=version - timedelta(seconds=2),
                                       expected_month="2026-01",
                                       verified_months={"2026-01"})
        assert db.get(ConversationTask, cid).status == "needs_account"
        assert mark_task_completed(db, conversation_id=cid, user_id=1,
                                   resumed_version=version,
                                   expected_month="2026-01",
                                   verified_months={"2026-01"})
        assert db.get(ConversationTask, cid).status == "completed"


def test_other_bill_read_does_not_close_unresumed_goal(client, auth_headers, monkeypatch):
    class Model:
        mode = "openai"
        async def stream(self, messages, tools=None):
            if tools and not any(item.get("role") == "tool" for item in messages):
                yield LLMChunk(tool_calls=[{
                    "id": "call_other_month", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-02"}'},
                }])
            else:
                yield LLMChunk(content="查询结果已显示。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    cid = client.post("/api/chat/conversations", headers=auth_headers,
                      json={}).json()["id"]
    url = f"/api/chat/conversations/{cid}/messages"
    with Session(get_engine()) as db:
        remember_pending_task(db, conversation_id=cid, user_id=1,
                              goal=ReadGoal("bill_analysis", "2026-01"))
        account_id = db.exec(select(Account)).first().id
    events = _events(client.post(url, headers=auth_headers, json={
        "content": "查2026-02的账单",
        "references": [{"kind": "account", "id": account_id}],
    }))
    assert any(event["type"] == "bill_result" for event in events)
    assert events[-1]["type"] == "done"
    with Session(get_engine()) as db:
        task = pending_task(db, conversation_id=cid, user_id=1)
        assert task is not None
        assert task.month == "2026-01"


def _bill(categories, consumption=15000, account_name="模拟活期"):
    return [("get_monthly_bill", {"ok": True, "data": {
        "month": "2026-01", "account_name": account_name,
        "masked_number": "****1234", "consumption_fen": consumption,
        "categories": categories, "ignored_count": 1,
    }})]


def test_verified_bill_analysis_has_useful_safe_fallback():
    source = _bill([
        {"category": "餐饮", "amount_fen": 10000, "count": 2},
        {"category": "交通", "amount_fen": 5000, "count": 2},
    ])
    summary = summarize_bill_insights(source, "分析这个月的消费结构")
    assert "餐饮支出最高" in summary and "交通" in summary
    assert "不能证明消费变化的原因" in summary
    assert "未纳入统计" in summary
    assert summarize_bill_insights(source, "查询账单") is None
    assert summarize_bill_insights(source, "分析为什么消费增加") is None
    assert summarize_bill_insights(_bill([
        {"category": "餐饮", "amount_fen": 10000, "count": 2},
        {"category": "交通", "amount_fen": 5000, "count": 2},
    ], account_name="账户 [敏感号码已隐藏]"), "分析账单") is None
    assert summarize_bill_insights(_bill([
        {"category": "恶意12345", "amount_fen": 15000, "count": 2},
    ]), "分析账单") is None
    assert summarize_bill_insights(_bill([
        {"category": "餐饮", "amount_fen": 9000, "count": 2},
    ]), "分析账单") is None
