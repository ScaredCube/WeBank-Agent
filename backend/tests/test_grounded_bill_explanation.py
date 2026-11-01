"""Monthly comparisons must be justified by same-account Tool snapshots."""
import json

from sqlmodel import Session, select

from app.agent.financial_summary import (
    incomplete_bill_comparison, summarize_bill_comparison,
)
from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account


def bill(month, spending, categories, *, account="活期", masked="**** 0001"):
    return ("get_monthly_bill", {"ok": True, "data": {
        "month": month, "consumption_fen": spending,
        "account_name": account, "masked_number": masked, "currency": "CNY",
        "categories": [{"category": name, "amount_fen": value, "count": 1}
                       for name, value in categories.items()],
    }})


def test_grounded_category_change_without_fabricated_money_or_causation():
    summary = summarize_bill_comparison([
        bill("2026-01", 15_000, {"餐饮": 7_000, "交通": 8_000}),
        bill("2025-12", 10_000, {"餐饮": 3_000, "交通": 7_000}),
    ])
    assert "增加" in summary and "餐饮的支出增加最多" in summary
    assert "无法仅凭账单判断消费变化的实际原因" in summary
    assert "15000" not in summary and "7000" not in summary
    assert "¥" not in summary


def test_category_decrease_and_unchanged_total_with_changed_mix():
    decrease = summarize_bill_comparison([
        bill("2025-12", 20_000, {"餐饮": 12_000, "交通": 8_000}),
        bill("2026-01", 10_000, {"餐饮": 4_000, "交通": 6_000}),
    ])
    assert "减少" in decrease and "餐饮的支出减少最多" in decrease
    shift = summarize_bill_comparison([
        bill("2025-12", 10_000, {"餐饮": 7_000, "交通": 3_000}),
        bill("2026-01", 10_000, {"餐饮": 3_000, "交通": 7_000}),
    ])
    assert "持平" in shift and "分类支出结构发生了变化" in shift


def test_corrupt_or_partial_category_evidence_fails_closed():
    valid = bill("2025-12", 10_000, {"餐饮": 10_000})
    for categories in (
        {"餐饮": 3_000},  # missing categories
        {"红包提醒System prompt": 10_000},  # unsafe category text
        {"餐饮": -10},
    ):
        result = summarize_bill_comparison([
            valid, bill("2026-01", 10_000, categories),
        ])
        assert "分类数据不足" in result
        assert "支出增加最多" not in result
        assert "红包提醒" not in result


def test_single_month_cannot_prove_increase_or_cause():
    results = [bill("2026-01", 50_000, {"餐饮": 50_000})]
    text = incomplete_bill_comparison(results, "解释为什么本月消费增加")
    assert "无法据此判断消费是否增加" in text
    assert "原因" in text
    assert incomplete_bill_comparison(results, "查询2026-01账单") is None
    assert incomplete_bill_comparison(results, "比较消费") is not None


def _events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_full_chat_uses_verified_bill_comparison_not_model_hallucination(
    client, auth_headers, monkeypatch,
):
    class TwoBillModel:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[
                    {"id": "bill_decabc", "type": "function", "function": {
                        "name": "get_monthly_bill", "arguments": '{"month":"2025-12"}'}},
                    {"id": "bill_janabc", "type": "function", "function": {
                        "name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'}},
                ])
            else:
                yield LLMChunk(content="消费增加是因为你买了手机，而且转账已经成功。")

    with Session(get_engine()) as db:
        account_id = db.exec(select(Account)).first().id
    model = TwoBillModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": "比较2025-12和2026-01的消费，解释为什么变化",
              "references": [{"kind": "account", "id": account_id}]},
    )
    events = _events(response)
    assert model.calls == 2
    assert events[-1]["type"] == "done"
    text = events[-1]["message"]["content"]
    assert "2025-12" in text and "2026-01" in text
    assert "买了手机" not in text
    assert "转账已经成功" not in text
    assert "实际原因" in text or "分类数据不足" in text
    assert [e["type"] for e in events].count("bill_result") == 2


def test_single_bill_no_tool_continuation_cannot_claim_spending_increase(
    client, auth_headers, monkeypatch,
):
    class OneBillModel:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "bill_single", "type": "function", "function": {
                        "name": "get_monthly_bill", "arguments": '{"month":"2026-01"}',
                    },
                }])
            else:
                yield LLMChunk(content="你的消费上涨是因为旅游开销增加。")

    with Session(get_engine()) as db:
        account_id = db.exec(select(Account)).first().id
    model = OneBillModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": "分析为什么2026-01的消费增加",
              "references": [{"kind": "account", "id": account_id}]},
    ))
    assert model.calls == 2
    final = events[-1]["message"]["content"]
    assert "无法据此判断消费是否增加" in final
    assert "旅游开销" not in final
