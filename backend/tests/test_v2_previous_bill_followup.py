"""Encrypted verified results, not chat prose, answer a narrow cross-turn follow-up."""
import json
from datetime import timedelta

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, ConversationSelection
from app.services.bill_followups import (
    asks_about_previous_bill_categories, verified_previous_bill_summary,
)
from tests.test_v2_durable_read_task import _events


def test_only_narrow_previous_bill_questions_are_cached():
    assert asks_about_previous_bill_categories("从刚才的账单中，哪些支出类别值得关注？")
    assert not asks_about_previous_bill_categories("从刚才的账单中为什么消费增加？")
    assert not asks_about_previous_bill_categories("比较上个月和刚才的账单")
    assert not asks_about_previous_bill_categories("转账100元，从刚才的账单里扣")


def test_saved_bill_followup_uses_verified_encrypted_snapshot(
    client, auth_headers, monkeypatch,
):
    monkeypatch.setattr(settings, "generative_ui_enabled", False)
    class FakeModel:
        mode = "openai"
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if tools and not any(row.get("role") == "tool" for row in messages):
                yield LLMChunk(tool_calls=[{
                    "id": "bill_cached_v2", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'},
                }])
            else:
                yield LLMChunk(content=json.dumps({
                    "narrative": "这份账单可以先从消费分类结构入手，单凭分类不足以解释支出变化。",
                }, ensure_ascii=False))
    model = FakeModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", headers=auth_headers, json={}).json()["id"]
    with Session(get_engine()) as db:
        account = db.exec(select(Account)).first()
        account_id, name, mask = account.id, account.name, account.masked_number
    endpoint = f"/api/chat/conversations/{cid}/messages"
    one = _events(client.post(endpoint, headers=auth_headers, json={
        "content": "分析2026-01的消费结构",
        "references": [{"kind": "account", "id": account_id}],
    }))
    assert one[-1]["type"] == "done"
    assert any(event["type"] == "bill_result" for event in one)
    call_count = model.calls
    two = _events(client.post(endpoint, headers=auth_headers, json={
        "content": "从刚才的账单中，哪些支出类别值得关注？",
    }))
    assert two[-1]["type"] == "done"
    answer = two[-1]["message"]["content"]
    assert answer.startswith("根据这段会话此前已核验并保存的账单")
    assert "支出最高" in answer
    assert model.calls == call_count  # No speculative model read or repeated bank tool.
    assert all(event["type"] not in {"bill_result", "action_required"} for event in two)
    with Session(get_engine()) as db:
        selection = db.get(ConversationSelection, cid)
        assert selection is not None
        assert verified_previous_bill_summary(
            db, conversation_id=cid, user_id=1, masked_number=mask,
            account_name="其他账户", selection_time=selection.updated_at,
        ) is None
        assert verified_previous_bill_summary(
            db, conversation_id=cid, user_id=999, masked_number=mask,
            account_name=name, selection_time=selection.updated_at,
        ) is None
        assert verified_previous_bill_summary(
            db, conversation_id=cid, user_id=1, masked_number=mask,
            account_name=name, selection_time=utcnow()+timedelta(hours=1),
        ) is None
    saved = client.get(endpoint, headers=auth_headers).json()
    assert saved[-1]["content"] == answer
