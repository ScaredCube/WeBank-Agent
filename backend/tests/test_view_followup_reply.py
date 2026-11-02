from app.agent.view_followup import render_view_followup
import asyncio


def test_selected_category_followup_uses_only_trusted_summary():
    reply = render_view_followup("这个分类有什么值得注意？", {
        "selected_category": "餐饮", "selected_category_amount_fen": 12345,
        "selected_category_count": 3, "selected_category_month": "2026-10",
    })
    assert "餐饮" in reply and "123.45" in reply and "3" in reply
    assert "原因" in reply


def test_view_context_cannot_turn_financial_action_into_an_answer():
    assert render_view_followup("请转账100元", {
        "selected_category": "餐饮", "selected_category_amount_fen": 12345,
        "selected_category_count": 3, "selected_category_month": "2026-10",
    }) is None


def test_view_context_does_not_swallow_an_additional_read_request():
    assert render_view_followup("这个分类有什么值得注意？顺便查一下余额", {
        "selected_category": "餐饮", "selected_category_amount_fen": 12345,
        "selected_category_count": 3, "selected_category_month": "2026-10",
    }) is None


def test_agent_no_tool_reply_uses_verified_view_selection():
    from app.agent.loop import AgentLoop
    from app.agent.llm import LLMChunk

    class Provider:
        mode = "openai"
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            yield LLMChunk(content="我无法确认。")

    async def run():
        provider = Provider()
        loop = AgentLoop(llm=provider)
        events = [event async for event in loop.stream(
            [{"role": "user", "content": "这个分类有什么值得注意？"}], user_id=1,
            original_request="这个分类有什么值得注意？", view_selection={
                "selected_category": "餐饮", "selected_category_amount_fen": 12345,
                "selected_category_count": 3, "selected_category_month": "2026-10",
            })]
        return provider.calls, events

    calls, result = asyncio.run(run())
    assert calls == 1  # V2 runs a separate tool-free wording pass.
    assert len(result) == 1 and result[0].type == "delta"
    assert "餐饮" in result[0].data["text"] and "123.45" in result[0].data["text"]
