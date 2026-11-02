"""One bounded extra chance to satisfy a missing explicit read-only goal."""
import json

from app.agent.compound_read_summary import missing_read_goal_for_retry
from app.agent.llm import LLMChunk


REQUEST = "查询最近交易流水，并检查是否有重复订阅"


def transaction_rows():
    return ("list_recent_transactions", {"ok": True, "data": [{
        "direction": "expense", "amount_fen": 100,
    }]})


def detected():
    return ("detect_subscriptions", {"ok": True, "data": []})


def tool(name, call_id="tool_abc"):
    args = '{"limit":5}' if name == "list_recent_transactions" else "{}"
    return {
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": args},
    }


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def run_chat(client, headers, monkeypatch, model, request=REQUEST):
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=headers).json()["id"]
    return events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=headers, json={"content": request},
    ))


def test_only_unattempted_explicit_read_goal_is_eligible():
    assert missing_read_goal_for_retry(
        [transaction_rows()], user_request=REQUEST,
    ) == "detect_subscriptions"
    # "识别" contains the character "别": never read it as "别查".
    assert missing_read_goal_for_retry(
        [transaction_rows()],
        user_request="请查最近交易流水，并识别重复订阅，说明值得关注的情况",
    ) == "detect_subscriptions"
    assert missing_read_goal_for_retry(
        [detected()], user_request=REQUEST,
    ) == "list_recent_transactions"
    assert missing_read_goal_for_retry(
        [("detect_subscriptions", {"ok": True, "data": []})],
        user_request=REQUEST,
    ) == "list_recent_transactions"
    for text in (
        "只查最近交易，订阅下次再说",
        "查询交易但不要排查订阅",
        "查询交易，暂不考虑订阅",
        "查询交易，订阅不用了",
        "查询交易和订阅并帮我取消",
        "查询交易并转账，顺便查订阅",
        "查询账单、交易流水和疑似重复订阅",
        "查询余额、交易和疑似订阅",
    ):
        assert missing_read_goal_for_retry(
            [transaction_rows()], user_request=text,
        ) is None


def test_failed_or_already_attempted_goal_is_not_retried():
    assert missing_read_goal_for_retry(
        [("list_recent_transactions", {"ok": False, "error": "请指定账户"})],
        user_request=REQUEST,
    ) is None
    assert missing_read_goal_for_retry(
        [transaction_rows(), detected()], user_request=REQUEST,
    ) is None
    assert missing_read_goal_for_retry(
        [transaction_rows(), ("detect_subscriptions", {"ok": False, "error": "失败"})],
        user_request=REQUEST,
    ) is None
    assert missing_read_goal_for_retry(
        [("get_account_balance", {"ok": True, "data": []})],
        user_request=REQUEST,
    ) is None


def test_model_can_complete_missing_second_read_goal_once(
    client, auth_headers, monkeypatch,
):
    class Interrupted:
        calls = 0
        system_nudge = ""

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[tool("list_recent_transactions")])
            elif self.calls == 2:
                yield LLMChunk(content="交易查询完成，订阅也查过了。")
            elif self.calls == 3:
                assert messages[-1]["role"] == "system"
                self.system_nudge = messages[-1]["content"]
                yield LLMChunk(tool_calls=[tool("detect_subscriptions", "subscriptions_abc")])
            else:
                yield LLMChunk(content="取消订阅已完成。")

    model = Interrupted()
    seen = run_chat(client, auth_headers, monkeypatch, model)
    assert model.calls == 4
    assert "尚未尝试的工具为 detect_subscriptions" in model.system_nudge
    assert seen[-1]["type"] == "done"
    reply = seen[-1]["message"]["content"]
    assert "最近交易查询" in reply and "周期性扣费" in reply
    assert "取消订阅已完成" not in reply
    assert "尚未完成可核验的周期性扣费识别" not in reply
    assert "action_required" not in [event["type"] for event in seen]


def test_retry_is_bounded_and_falls_back_to_truthful_partial_answer(
    client, auth_headers, monkeypatch,
):
    class Uncooperative:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[tool("list_recent_transactions")])
            else:
                yield LLMChunk(content="两个目标都已完成。")

    model = Uncooperative()
    seen = run_chat(client, auth_headers, monkeypatch, model)
    assert model.calls == 3
    answer = seen[-1]["message"]["content"]
    assert "尚未完成可核验的周期性扣费识别" in answer
    assert "两个目标都已完成" not in answer


def test_retry_cannot_invoke_unrequested_write_tool(
    client, auth_headers, monkeypatch,
):
    class Hostile:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[tool("list_recent_transactions")])
            elif self.calls == 2:
                yield LLMChunk(content="订阅已核验。")
            else:
                yield LLMChunk(tool_calls=[{
                    "id": "forged_write", "type": "function",
                    "function": {"name": "prepare_transfer", "arguments": "{}"},
                }])

    model = Hostile()
    seen = run_chat(client, auth_headers, monkeypatch, model)
    assert model.calls == 3
    reply = seen[-1]["message"]["content"]
    assert "尚未完成可核验的周期性扣费识别" in reply
    assert "action_required" not in [event["type"] for event in seen]


def test_retry_does_not_override_user_skip(
    client, auth_headers, monkeypatch,
):
    class Model:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[tool("list_recent_transactions")])
            else:
                yield LLMChunk(content="结束。")

    model = Model()
    seen = run_chat(
        client, auth_headers, monkeypatch, model,
        request="只查询最近交易流水，订阅不用检查",
    )
    assert model.calls == 2
    assert "尚未完成可核验的周期性扣费识别" not in seen[-1]["message"]["content"]
