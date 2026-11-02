"""Verify exact same-turn read reuse and failure recovery, without new authority."""
import json

from app.agent.llm import LLMChunk
from app.agent.read_result_recovery import read_cache_key, verified_partial_read_reply
from app.agent.tool_executor import ToolExecutor, ToolExecutionOutcome


def call(name, id_, arguments="{}"):
    return {
        "id": id_, "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def events(client, headers, monkeypatch, model, message):
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    conversation = client.post(
        "/api/chat/conversations", json={}, headers=headers,
    ).json()["id"]
    response = client.post(
        f"/api/chat/conversations/{conversation}/messages",
        json={"content": message}, headers=headers,
    )
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_fingerprint_only_caches_explicit_read_tools():
    assert read_cache_key("get_monthly_bill", '{"month":"2026-01","x":1}') == (
        "get_monthly_bill", '{"month":"2026-01","x":1}',
    )
    assert read_cache_key("get_monthly_bill", '{"x":1,"month":"2026-01"}') == (
        "get_monthly_bill", '{"month":"2026-01","x":1}',
    )
    assert read_cache_key("get_monthly_bill", "{bad") is None
    assert read_cache_key("get_monthly_bill", "[]") is None
    for name in (
        "prepare_transfer", "prepare_internal_transfer",
        "get_latest_action_progress", "get_account_balance",
        "get_subscriptions", "calculate",
    ):
        assert read_cache_key(name, "{}") is None


def test_duplicate_read_in_same_batch_runs_once_and_other_goal_runs(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute
    calls = []

    async def counted(self, tool_call, context, prior_calls):
        calls.append(tool_call["function"]["name"])
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", counted)

    class Model:
        rounds = 0

        async def stream(self, messages, tools=None):
            self.rounds += 1
            if self.rounds == 1:
                yield LLMChunk(tool_calls=[
                    call("list_recent_transactions", "tx_1", '{"limit":5}'),
                    call("list_recent_transactions", "tx_2", '{"limit": 5}'),
                    call("detect_subscriptions", "subs_1"),
                ])
            else:
                # The model must receive one response per call_id.
                tool_messages = [m for m in messages if m.get("role") == "tool"]
                assert len(tool_messages) == 3
                assert json.loads(tool_messages[0]["content"]) == json.loads(
                    tool_messages[1]["content"],
                )
                yield LLMChunk(content="我已经取消订阅并扣款了。")

    model = Model()
    found = events(
        client, auth_headers, monkeypatch, model,
        "查询最近交易流水，并识别重复订阅",
    )
    assert calls.count("list_recent_transactions") == 1
    assert calls.count("detect_subscriptions") == 1
    answer = found[-1]["message"]["content"]
    assert "查询范围说明" in answer
    assert "已取消订阅" not in answer
    assert answer.count("模拟交易记录：") <= 1


def test_duplicate_read_only_round_stops_with_verified_partial_reply(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute
    called = []

    async def counted(self, tool_call, context, prior_calls):
        called.append(tool_call["function"]["name"])
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", counted)

    class Repeat:
        rounds = 0

        async def stream(self, messages, tools=None):
            self.rounds += 1
            if self.rounds == 1:
                yield LLMChunk(tool_calls=[call(
                    "list_recent_transactions", "tx_first", '{"limit":5}',
                )])
            else:
                yield LLMChunk(tool_calls=[call(
                    "list_recent_transactions", "tx_repeat", '{"limit": 5}',
                )])

    model = Repeat()
    found = events(
        client, auth_headers, monkeypatch, model,
        "查询最近交易流水，并检查重复订阅",
    )
    assert model.rounds == 2
    assert called == ["list_recent_transactions"]
    assert found[-1]["type"] == "done"
    answer = found[-1]["message"]["content"]
    assert "部分只读查询已完成" in answer
    assert "订阅识别" in answer or "周期性扣费识别" in answer


def test_distinct_months_are_not_reused_and_both_cards_are_recorded(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute
    months = []

    async def counted(self, tool_call, context, prior_calls):
        months.append(json.loads(tool_call["function"]["arguments"]).get("month"))
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", counted)

    class Compare:
        rounds = 0

        async def stream(self, messages, tools=None):
            self.rounds += 1
            if self.rounds == 1:
                yield LLMChunk(tool_calls=[
                    call("get_monthly_bill", "bill_dec", '{"month":"2025-12"}'),
                    call("get_monthly_bill", "bill_jan", '{"month":"2026-01"}'),
                ])
            else:
                yield LLMChunk(content="请看下方结果。")

    found = events(
        client, auth_headers, monkeypatch, Compare(),
        "比较2025-12和2026-01的月度账单",
    )
    assert months == ["2025-12", "2026-01"]
    assert [e["type"] for e in found].count("bill_result") == 2
    assert found[-1]["type"] == "done"


def test_later_tool_failure_preserves_prior_verified_transaction(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute

    async def broken_second(self, tool_call, context, prior_calls):
        if tool_call["function"]["name"] == "detect_subscriptions":
            raise RuntimeError("INTERNAL_MARKER_DO_NOT_DISPLAY")
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", broken_second)

    class Two:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[
                call("list_recent_transactions", "tx_good", '{"limit":5}'),
                call("detect_subscriptions", "subs_bad"),
            ])

    found = events(
        client, auth_headers, monkeypatch, Two(),
        "查询最近交易流水，并检查重复订阅",
    )
    assert [e["type"] for e in found] == ["delta", "done"]
    answer = found[-1]["message"]["content"]
    assert "部分只读查询已完成" in answer
    assert "尚未完成可核验的周期性扣费识别" in answer
    assert "INTERNAL_MARKER" not in answer
    assert "模拟交易记录" in answer


def test_model_failure_after_verified_read_preserves_result(
    client, auth_headers, monkeypatch,
):
    class ModelBreak:
        rounds = 0

        async def stream(self, messages, tools=None):
            self.rounds += 1
            if self.rounds == 1:
                yield LLMChunk(tool_calls=[call(
                    "list_recent_transactions", "tx_first", '{"limit":5}',
                )])
            else:
                raise RuntimeError("PROVIDER_SECRET_ERROR")
                yield LLMChunk(content="impossible")

    found = events(
        client, auth_headers, monkeypatch, ModelBreak(),
        "查询最近交易流水，并检查重复订阅",
    )
    assert [e["type"] for e in found] == ["delta", "done"]
    answer = found[-1]["message"]["content"]
    assert "部分只读查询已完成" in answer
    assert "PROVIDER_SECRET_ERROR" not in answer


def test_no_trusted_result_still_returns_explicit_error(
    client, auth_headers, monkeypatch,
):
    class Broken:
        async def stream(self, messages, tools=None):
            raise RuntimeError("PRIVATE_ERROR")
            yield LLMChunk(content="impossible")

    found = events(
        client, auth_headers, monkeypatch, Broken(), "查询最近交易记录",
    )
    assert found[-1]["type"] == "error"
    assert "PRIVATE_ERROR" not in found[-1]["message"]


def test_write_tool_exception_does_not_claim_completion(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute

    async def broken_write(self, tool_call, context, prior_calls):
        if tool_call["function"]["name"] == "prepare_transfer":
            raise RuntimeError("ACTION_NOT_CONFIRMED")
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", broken_write)

    class Mixed:
        async def stream(self, messages, tools=None):
            yield LLMChunk(tool_calls=[
                call("list_recent_transactions", "tx_good", '{"limit":5}'),
                call("prepare_transfer", "attempted_write"),
            ])

    found = events(
        client, auth_headers, monkeypatch, Mixed(),
        "查询最近交易，并准备转账",
    )
    assert found[-1]["type"] == "error"
    assert "action_required" not in [e["type"] for e in found]


def test_attempted_nonread_invalidates_prior_read_snapshot_without_executing_money(
    client, auth_headers, monkeypatch,
):
    original = ToolExecutor.execute
    called = []

    async def counted(self, tool_call, context, prior_calls):
        name = tool_call["function"]["name"]
        called.append(name)
        if name == "prepare_internal_transfer":
            # Intentionally stubbed. Never perform a simulated financial write.
            return ToolExecutionOutcome(observation={
                "ok": False, "data": None, "error": "缺少必要操作条件",
            })
        return await original(self, tool_call, context, prior_calls)

    monkeypatch.setattr(ToolExecutor, "execute", counted)

    class Model:
        rounds = 0

        async def stream(self, messages, tools=None):
            self.rounds += 1
            if self.rounds == 1:
                yield LLMChunk(tool_calls=[call(
                    "list_recent_transactions", "tx_before", '{"limit":5}',
                )])
            elif self.rounds == 2:
                yield LLMChunk(tool_calls=[
                    call("prepare_internal_transfer", "write_stub"),
                    call("list_recent_transactions", "tx_after", '{"limit":5}'),
                ])
            else:
                yield LLMChunk(content="操作已完成")

    found = events(
        client, auth_headers, monkeypatch, Model(),
        "查询交易流水，再准备内部转账，最后重新查询交易",
    )
    assert called == [
        "list_recent_transactions", "prepare_internal_transfer",
        "list_recent_transactions",
    ]
    assert "action_required" not in [e["type"] for e in found]


def test_partial_reply_rejects_unverified_or_malformed_results():
    assert verified_partial_read_reply(
        [("list_recent_transactions", {"ok": False, "error": "no"})],
        user_request="查询交易",
    ) is None
    assert verified_partial_read_reply(
        [("prepare_transfer", {"ok": True, "data": {"status": "completed"}})],
        user_request="转账",
    ) is None
