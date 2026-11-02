"""Compounded read answers derive completion and caution only from Tool results."""
import json

from app.agent.compound_read_summary import summarize_transaction_subscription_review
from app.agent.llm import LLMChunk


REQUEST = "请查最近交易流水，并识别重复订阅，说明值得关注的情况"


def tx(items):
    return ("list_recent_transactions", {"ok": True, "data": items, "error": None})


def detect(items):
    return ("detect_subscriptions", {"ok": True, "data": items, "error": None})


def row(amount=4200):
    return {
        "direction": "expense", "amount_fen": amount,
        "category": "软件服务", "counterparty": "商家甲",
        "occurred_at": "2026-10-15T08:00:00",
    }


def candidate():
    return {
        "merchant": "商家甲", "amount_fen": 4200, "occurrences": 3,
        "last_occurred_at": "2026-10-15T08:00:00",
        "suggested_cycle": "monthly",
    }


def test_both_tools_ground_completion_and_do_not_confirm_duplicate():
    result = summarize_transaction_subscription_review(
        [tx([row(), row(2100)]), detect([candidate()])],
        user_request=REQUEST,
    )
    assert "本次返回 2 笔" in result
    assert "识别到 1 项疑似周期性扣费线索" in result
    assert "不能单凭这些记录认定存在重复订阅" in result
    assert "4200" not in result and "商家甲" not in result


def test_empty_candidates_is_not_proof_there_are_no_subscriptions():
    result = summarize_transaction_subscription_review(
        [tx([row()]), detect([])], user_request=REQUEST,
    )
    assert "未从近186天" in result
    assert "不能单凭这些记录认定" in result
    assert "没有重复订阅" not in result


def test_missing_goal_explicitly_stays_incomplete():
    text = summarize_transaction_subscription_review(
        [tx([row()])], user_request=REQUEST,
    )
    assert "尚未完成可核验的周期性扣费识别" in text
    assert "已经检查" not in text
    other = summarize_transaction_subscription_review(
        [detect([candidate()])], user_request=REQUEST,
    )
    assert "尚未取得可核验的最近交易列表" in other


def test_one_goal_keeps_existing_answer_path_and_other_tools_do_not_interfere():
    assert summarize_transaction_subscription_review(
        [tx([row()])], user_request="查询最近交易",
    ) is None
    assert summarize_transaction_subscription_review(
        [detect([candidate()])], user_request="检测订阅",
    ) is None
    assert summarize_transaction_subscription_review(
        [tx([row()]), ("get_monthly_bill", {"ok": True, "data": {}})],
        user_request=REQUEST,
    ) is None


def test_user_explicitly_skips_subscription_detection_is_not_nagged():
    for request in (
        "只查交易，订阅下次再说",
        "查询交易，但不需要检查订阅",
        "看一下交易流水，不要排查自动扣费",
    ):
        assert summarize_transaction_subscription_review(
            [tx([row()])], user_request=request,
        ) is None


def test_failed_or_malformed_data_does_not_claim_verification():
    failed = ("detect_subscriptions", {"ok": False, "error": "查询失败"})
    text = summarize_transaction_subscription_review(
        [tx([row()]), failed], user_request=REQUEST,
    )
    assert "尚未完成可核验的周期性扣费识别" in text
    invalid = detect([{"merchant": "商家甲", "occurrences": 1, "amount_fen": 20}])
    text = summarize_transaction_subscription_review(
        [tx([row()]), invalid], user_request=REQUEST,
    )
    assert "尚未完成可核验的周期性扣费识别" in text


def test_cancellation_is_never_inferred_from_read_only_tools():
    text = summarize_transaction_subscription_review(
        [tx([row()]), detect([candidate()])],
        user_request="查询交易并识别重复订阅，取消重复的",
    )
    assert "不代表已经取消任何订阅" in text


def events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_chat_compound_two_tool_result_overrides_model_forged_completion(
    client, auth_headers, monkeypatch,
):
    class Model:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[
                    {
                        "id": "txn_compound", "type": "function",
                        "function": {"name": "list_recent_transactions",
                                     "arguments": '{"limit": 5}'},
                    },
                    {
                        "id": "detect_compound", "type": "function",
                        "function": {"name": "detect_subscriptions",
                                     "arguments": "{}"},
                    },
                ])
            else:
                yield LLMChunk(content="我已经帮你取消了重复订阅，并核实多扣了9999元。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    seen = events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": REQUEST},
    ))
    assert model.calls == 2
    assert seen[-1]["type"] == "done"
    reply = seen[-1]["message"]["content"]
    assert "最近交易查询" in reply
    assert "周期性扣费线索" in reply
    assert "单个模拟账户" in reply and "本人所有模拟账户近186天" in reply
    assert "模拟交易记录" in reply or "没有查询到模拟交易记录" in reply
    assert "多扣了9999" not in reply
    assert "帮你取消了" not in reply
    assert "action_required" not in [item["type"] for item in seen]


def test_chat_partial_tool_result_does_not_claim_both_goals_completed(
    client, auth_headers, monkeypatch,
):
    class Model:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "txn_partial", "type": "function",
                    "function": {"name": "list_recent_transactions",
                                 "arguments": '{"limit": 5}'},
                }])
            else:
                yield LLMChunk(content="交易查询和订阅排查都完成了，没任何问题。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    seen = events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": REQUEST},
    ))
    # One bounded extra turn is now allowed to complete the missing goal.
    # This model declines; the final answer must still disclose the gap.
    assert model.calls == 3
    reply = seen[-1]["message"]["content"]
    assert "尚未完成可核验的周期性扣费识别" in reply
    assert "都完成了" not in reply
