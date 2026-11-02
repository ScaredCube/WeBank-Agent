"""The output reviewer is separate from the tool Guard and rewrites, not blocks."""
import asyncio
import json

import pytest

from app.agent.llm import LLMChunk
from app.agent.reply_grounding import (
    ReplyGrounding, ReplyGroundingError, ReplyGroundingRejected,
)


class ReviewModel:
    mode = "openai"

    def __init__(self, verdicts, rewrite="请告诉我你想查询哪个账户。"):
        self.verdicts = list(verdicts)
        self.rewrite = rewrite
        self.calls = []

    async def stream(self, messages, tools=None):
        self.calls.append((messages, tools))
        system = messages[0]["content"]
        if "最终回复事实审查器" in system:
            verdict = self.verdicts.pop(0)
            yield LLMChunk(content=json.dumps(verdict, ensure_ascii=False))
        elif "必须重写" in system:
            yield LLMChunk(content=self.rewrite)
        else:  # pragma: no cover
            yield LLMChunk(content="unexpected")


def run(coro):
    return asyncio.run(coro)


def test_grounded_reply_is_returned_without_rewrite():
    model = ReviewModel([{"grounded": True, "issues": []}])
    result = run(ReplyGrounding(model).compose(
        "我还没有查到可靠的银行数据。", user_request="查余额", tool_results=[],
    ))
    assert result == "我还没有查到可靠的银行数据。"
    assert len(model.calls) == 1 and model.calls[0][1] is None


def test_ungrounded_reply_is_rewritten_then_reviewed_again():
    model = ReviewModel(
        [{"grounded": False, "issues": ["unsupported_balance"]},
         {"grounded": True, "issues": []}],
        rewrite="请告诉我你想查询哪个账户，我再为你核实。",
    )
    result = run(ReplyGrounding(model).compose(
        "你的余额是 999 元。", user_request="查余额", tool_results=[],
    ))
    assert result == "请告诉我你想查询哪个账户，我再为你核实。"
    assert len(model.calls) == 3


def test_second_review_failure_raises_without_emitting_candidate():
    model = ReviewModel([
        {"grounded": False, "issues": ["unsupported_balance"]},
        {"grounded": False, "issues": ["unsupported_action_status"]},
    ])
    with pytest.raises(ReplyGroundingRejected):
        run(ReplyGrounding(model).compose(
            "已转账成功。", user_request="转账", tool_results=[],
        ))


def test_malformed_or_unavailable_verdict_fails_closed():
    class Broken(ReviewModel):
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="not json")

    with pytest.raises(ReplyGroundingError):
        run(ReplyGrounding(Broken([])).compose(
            "你好。", user_request="你好", tool_results=[],
        ))


def test_tool_facts_are_passed_to_the_reviewer_without_tokens():
    model = ReviewModel([{"grounded": True, "issues": []}])
    run(ReplyGrounding(model).compose(
        "账单已查询。", user_request="查账单",
        tool_results=[("get_monthly_bill", {
            "ok": True,
            "data": {"month": "2026-01", "expense_fen": 10000, "currency": "CNY"},
        })],
    ))
    payload = model.calls[0][0][-1]["content"]
    assert "2026-01" in payload or "账单" in payload
    assert "confirmation_token" not in payload
