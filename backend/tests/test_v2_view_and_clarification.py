"""V2: verified view continuation and missing-data clarification are tool-free."""
import asyncio
import json

from app.agent.loop import AgentLoop
from app.agent.llm import LLMChunk


_VIEW = {
    "selected_category": "餐饮",
    "selected_category_amount_fen": 12345,
    "selected_category_count": 3,
    "selected_category_month": "2026-10",
}


def test_view_selection_naturally_explained_without_authorizing_tools():
    class Model:
        mode = "openai"
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            assert tools is None
            assert "123.45" in messages[-1]["content"]
            yield LLMChunk(content=json.dumps({"narrative":
                "这一分类的支出已得到核实，但分类汇总只说明了消费规模，无法单凭它推断消费增加的原因。"
            }, ensure_ascii=False))
    async def run():
        model = Model()
        events = [e async for e in AgentLoop(llm=model).stream(
            [{"role": "user", "content": "这类消费为什么这么多？"}],
            user_id=1, original_request="这类消费为什么这么多？",
            view_selection=_VIEW,
        )]
        return model.calls, events
    calls, events = asyncio.run(run())
    assert calls == 1
    assert len(events) == 1
    assert "分类汇总" in events[0].data["text"]
    assert "123.45" in events[0].data["text"]


def test_no_bank_tool_read_request_gets_independent_followup_question():
    class Model:
        mode = "openai"
        calls = []
        async def stream(self, messages, tools=None):
            self.calls.append(tools is not None)
            if tools is not None:
                yield LLMChunk(content="我已经查到了你的余额为99999元。")
            else:
                yield LLMChunk(content=json.dumps({
                    "question": "请问你希望查询哪个账户的余额？"
                }, ensure_ascii=False))
    async def run():
        model = Model()
        events = [e async for e in AgentLoop(llm=model).stream(
            [{"role": "user", "content": "查询我的账户余额"}],
            user_id=1, original_request="查询我的账户余额",
        )]
        return model.calls, events
    calls, events = asyncio.run(run())
    assert calls == [True, False]
    assert len(events) == 1 and events[0].type == "delta"
    assert "99999" not in events[0].data["text"]
    assert "哪个账户" in events[0].data["text"]
