"""V2 reply generation keeps Tool facts authoritative."""
import asyncio
import json

from app.agent.llm import LLMChunk
from app.agent.response_synthesis import ResponseSynthesizer, TurnOutcome


class ReplyModel:
    mode = "openai"
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
    async def stream(self, messages, tools=None):
        self.calls.append((messages, tools))
        yield LLMChunk(content=json.dumps({"narrative": self.reply}, ensure_ascii=False))


def test_separate_model_generates_narrative_with_only_verified_numbers():
    model = ReplyModel("已经取得可信的账户资料，但余额不能替代月度收支分析；若要分析消费结构，还需要查询月度账单。")
    outcome = TurnOutcome(
        user_goal="分析本月收支",
        verified_results=(("get_account_balance", {"ok": True, "data": [
            {"name": "测试活期", "masked_number": "****1234", "balance_fen": 246800}
        ]}),),
        fallback_text="测试兜底",
    )
    text = asyncio.run(ResponseSynthesizer(model).compose(outcome))
    assert text.startswith("已经取得")
    assert "2,468.00 元" in text
    assert len(model.calls) == 1
    assert model.calls[0][1] is None


def test_unverified_number_or_action_claim_never_reaches_user():
    model = ReplyModel("我已经转账成功了，而且余额为99999元。")
    outcome = TurnOutcome(
        user_goal="查余额",
        verified_results=(("get_account_balance", {"ok": True, "data": [
            {"name": "测试活期", "masked_number": "****1234", "balance_fen": 246800}
        ]}),),
        fallback_text="只能展示可信余额",
    )
    assert asyncio.run(ResponseSynthesizer(model).compose(outcome)) == "只能展示可信余额"


def test_nonread_or_failed_result_does_not_trigger_second_model():
    model = ReplyModel("任意说明")
    outcome = TurnOutcome("转账", (("prepare_transfer", {"ok": False}),), "操作未完成")
    assert asyncio.run(ResponseSynthesizer(model).compose(outcome)) == "操作未完成"
    assert model.calls == []
