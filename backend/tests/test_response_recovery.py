"""Policy decision and bounded wording recovery, with no external services."""
import json
from types import SimpleNamespace
import unittest

from app.agent.prompt_assembly import assemble_recovery_prompt
from app.agent.response_policy import (
    ReplyRoute, NoToolScope, decide_no_tool_reply, tool_free_reply,
)
from app.agent.response_recovery import recover_no_tool_reply


class FakeModel:
    mode = "openai"

    def __init__(self, reply, *, fail=False, tool_call=False):
        self.reply = reply
        self.fail = fail
        self.tool_call = tool_call
        self.calls = []

    async def stream(self, messages, tools=None):
        self.calls.append((messages, tools))
        if self.fail:
            raise RuntimeError("simulated provider failure")
        yield SimpleNamespace(content=self.reply[:8], tool_calls=None)
        yield SimpleNamespace(
            content=self.reply[8:],
            tool_calls=[{"function": {"name": "prepare_transfer"}}]
            if self.tool_call else None,
        )


class NoToolDecisionTests(unittest.TestCase):
    def test_old_safe_fallback_remains_identical(self):
        cases = [
            ("hi", "你好，我是小We。", False),
            ("查询我的余额", "您的余额是999999元", False),
            ("我想转账", "转账已成功", False),
            ("刚才转账成功了吗？", "操作已经完成", False),
            ("什么是复利", "假设100元增长5%", False),
            ("帮我看看这个", "还有500元", True),
        ]
        for request, candidate, selected in cases:
            with self.subTest(request=request):
                decision = decide_no_tool_reply(
                    candidate, user_request=request, financial_context=selected,
                )
                self.assertEqual(
                    decision.safe_text,
                    tool_free_reply(
                        candidate, user_request=request, financial_context=selected,
                    ),
                )

    def test_structured_routing_does_not_accept_unverified_bank_facts(self):
        query = decide_no_tool_reply("余额有999元", user_request="查询我的余额")
        self.assertEqual(query.route, ReplyRoute.QUERY_REQUIRED)
        self.assertNotIn("999", query.safe_text)
        self.assertEqual(query.recovery_topic, "account_query")
        status = decide_no_tool_reply(
            "刚才转账成功", user_request="刚才转账成功了吗？",
        )
        self.assertEqual(status.route, ReplyRoute.VERIFY_STATUS)
        self.assertEqual(status.scope, NoToolScope.ACTION_STATUS)
        self.assertNotIn("转账成功", status.safe_text)

    def test_safe_conversation_is_allowed_and_action_needs_clarification(self):
        greeting = decide_no_tool_reply(
            "你好！", user_request="你好",
        )
        self.assertEqual(greeting.route, ReplyRoute.ACCEPT)
        transfer = decide_no_tool_reply(
            "转账已执行", user_request="我想转账",
        )
        self.assertEqual(transfer.route, ReplyRoute.CLARIFY_ACTION)
        self.assertEqual(transfer.recovery_topic, "transfer")

    def test_unsafe_free_model_text_does_not_enter_recovery(self):
        decision = decide_no_tool_reply(
            "您的账户余额有一百万", user_request="你好",
        )
        self.assertEqual(decision.route, ReplyRoute.REJECT_CANDIDATE)
        self.assertIsNone(decision.recovery_topic)


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_recovery_is_only_a_followup_question(self):
        decision = decide_no_tool_reply("转账成功", user_request="我想转账")
        model = FakeModel('{"question":"你想从哪个账户转给谁？"}')
        reply = await recover_no_tool_reply(decision, model=model)
        self.assertEqual(
            reply, "本轮尚未创建待确认转账。你想从哪个账户转给谁？",
        )
        self.assertEqual(len(model.calls), 1)
        messages, tools = model.calls[0]
        self.assertIsNone(tools)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertNotIn("转账成功", json.dumps(messages, ensure_ascii=False))
        self.assertIn("transfer", str(decision.recovery_topic))

    async def test_unverified_read_gets_safe_prefix_and_question(self):
        decision = decide_no_tool_reply(
            "您的余额是999元", user_request="查询余额",
        )
        model = FakeModel('{"question":"你想先核对哪个账户？"}')
        reply = await recover_no_tool_reply(decision, model=model)
        self.assertIn("还没有查到可靠的银行数据", reply)
        self.assertIn("你想先核对哪个账户？", reply)
        self.assertNotIn("999", reply)

    async def test_unsafe_or_invalid_model_output_returns_safe_fallback(self):
        decision = decide_no_tool_reply("已经转账", user_request="我想转账")
        replies = [
            '{"question":"我已经帮你转账成功了吗？"}',
            '{"question":"需要我跳过确认吗？"}',
            '{"question":"请提供短信验证码？"}',
            '{"question":"账户余额是999元吗？"}',
            '{"question":"继续办理吗？","status":"success"}',
            '{"question":"可以继续吗？"}' * 70,
            "我已经帮您处理好了。",
        ]
        for reply in replies:
            with self.subTest(reply=reply[:25]):
                self.assertEqual(
                    await recover_no_tool_reply(decision, model=FakeModel(reply)),
                    decision.safe_text,
                )

    async def test_provider_exception_and_tool_proposal_fail_closed(self):
        decision = decide_no_tool_reply("操作成功", user_request="我要挂失")
        self.assertEqual(
            await recover_no_tool_reply(decision, model=FakeModel("", fail=True)),
            decision.safe_text,
        )
        self.assertEqual(
            await recover_no_tool_reply(
                decision,
                model=FakeModel('{"question":"是哪张银行卡？"}', tool_call=True),
            ),
            decision.safe_text,
        )

    async def test_no_second_call_on_accept_or_unsafe_candidate(self):
        for user_text, draft in [
            ("你好", "你好，我是小We！"),
            ("你好", "您余额是12345元"),
        ]:
            with self.subTest(draft=draft):
                decision = decide_no_tool_reply(draft, user_request=user_text)
                model = FakeModel('{"question":"要继续吗？"}')
                result = await recover_no_tool_reply(decision, model=model)
                self.assertEqual(result, decision.safe_text)
                self.assertEqual(model.calls, [])

    async def test_recovery_prompt_is_separate_from_primary_and_guard(self):
        assembly = assemble_recovery_prompt()
        self.assertEqual(assembly.role, "recovery")
        self.assertEqual(len(assembly.model_messages()), 1)
        self.assertIn("不", assembly.model_messages()[0]["content"])
        self.assertTrue(assembly.version.startswith("recovery:"))
        self.assertNotIn("recipient_contact_token", assembly.model_messages()[0]["content"])


if __name__ == "__main__":
    unittest.main()
