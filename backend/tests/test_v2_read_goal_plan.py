"""Explicit three-target READ plans are bounded by model intent and Tool evidence."""
import json

from app.agent.llm import LLMChunk
from app.agent.read_goal_plan import build_read_goal_plan
from tests.test_ui_chat_roundtrip import bill


REQUEST = "请查2026-10的月度账单、最近交易流水，并识别疑似重复订阅"


def call(name: str, cid: int):
    arguments = (
        '{"month":"2026-10"}' if name == "get_monthly_bill"
        else '{"limit":5}' if name == "list_recent_transactions"
        else "{}"
    )
    return {"id": f"plan_call_{cid}", "type": "function",
            "function": {"name": name, "arguments": arguments}}


def events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_plan_only_for_three_explicit_safe_read_objectives():
    assert build_read_goal_plan(REQUEST).goals == (
        "get_monthly_bill", "list_recent_transactions", "detect_subscriptions",
    )
    for request in (
        "查询账单", "查询交易流水与疑似订阅",
        "查询账单、交易流水和疑似重复订阅并取消订阅",
        "帮我查账单、交易流水、疑似订阅然后转账",
        "请查账单和交易流水，订阅暂不检查",
        "只查账单，不用查交易流水和疑似订阅",
        "解释什么是账单", "查询余额、最近交易和订阅",
    ):
        assert build_read_goal_plan(request) is None


def test_verified_observations_drive_progress_and_failed_tools_are_not_retried():
    plan = build_read_goal_plan(REQUEST)
    snapshot = ("get_monthly_bill", {"ok": True,
                 "data": bill("2026-10", 12000, 6000)})
    assert plan.next_unattempted([snapshot]) == "list_recent_transactions"
    assert plan.next_unattempted([snapshot, (
        "list_recent_transactions", {"ok": True, "data": []},
    )]) == "detect_subscriptions"
    assert plan.next_unattempted([snapshot, (
        "list_recent_transactions", {"ok": False, "error": "权限不足"},
    )]) is None
    assert plan.next_unattempted([snapshot, ("prepare_transfer", {"ok": True})]) is None
    summary = plan.report([snapshot])
    assert "未完成全部请求" in summary
    assert "最近交易流水：未取得可信结果" in summary
    assert "三个只读查询目标均已" not in summary


def test_multi_goal_chat_finishes_missing_reads_without_claiming_cancellation(
    client, auth_headers, monkeypatch,
):
    class Model:
        calls = 0
        proposed = []
        nudges = []

        async def stream(self, messages, tools=None):
            self.calls += 1
            if messages[-1]["role"] == "system":
                self.nudges.append(messages[-1]["content"])
            if self.calls == 1:
                yield LLMChunk(tool_calls=[call("get_monthly_bill", 1)])
            elif self.calls == 2:
                yield LLMChunk(content="三个查询已经全部完成。")
            elif self.calls == 3:
                self.proposed.append("list_recent_transactions")
                yield LLMChunk(tool_calls=[call("list_recent_transactions", 2)])
            elif self.calls == 4:
                yield LLMChunk(content="都已经查到了。")
            elif self.calls == 5:
                self.proposed.append("detect_subscriptions")
                yield LLMChunk(tool_calls=[call("detect_subscriptions", 3)])
            else:
                yield LLMChunk(content="已为你取消全部重复订阅。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    reply = events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers, json={"content": REQUEST},
    ))
    assert reply[-1]["type"] == "done"
    text = reply[-1]["message"]["content"]
    assert model.calls == 6
    assert model.proposed == ["list_recent_transactions", "detect_subscriptions"]
    assert len(model.nudges) == 2
    assert "三个只读查询目标均已取得可信结果" in text
    assert "不代表已确认重复扣费" in text
    assert "已为你取消全部重复订阅" not in text
    assert "action_required" not in [frame["type"] for frame in reply]


def test_uncooperative_model_cannot_repeatedly_ask_or_inject_write_tool(
    client, auth_headers, monkeypatch,
):
    class Model:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[call("get_monthly_bill", 1)])
            elif self.calls == 2:
                yield LLMChunk(content="全部完成")
            else:
                yield LLMChunk(tool_calls=[call("prepare_transfer", 2)])

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    reply = events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers, json={"content": REQUEST},
    ))
    assert model.calls == 3
    assert reply[-1]["type"] == "done"
    text = reply[-1]["message"]["content"]
    assert "尚未完成全部请求" in text
    assert "最近交易流水：未取得可信结果" in text
    assert "action_required" not in [frame["type"] for frame in reply]


def test_multi_goal_task_survives_missing_account_and_completes_on_all_evidence(
    client, auth_headers, monkeypatch,
):
    from sqlmodel import Session, select
    from app.db.session import get_engine
    from app.models import ConversationTask, Account

    class Model:
        mode = "openai"
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            latest = str(messages[-1].get("content") or "")
            if tools is None:
                yield LLMChunk(content=json.dumps({
                    "question": "请先选择要查询的账户，我会继续完成账单、交易及订阅识别。"
                }, ensure_ascii=False))
            elif "服务端保存的未完成只读目标" in latest:
                yield LLMChunk(tool_calls=[
                    call("get_monthly_bill", 21),
                    call("list_recent_transactions", 22),
                    call("detect_subscriptions", 23),
                ])
            elif any(item.get("role") == "tool" for item in messages):
                yield LLMChunk(content="模型认为任务结束。")
            else:
                yield LLMChunk(content="请先选择账户。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    endpoint = f"/api/chat/conversations/{cid}/messages"
    first = events(client.post(endpoint, headers=auth_headers,
                               json={"content": REQUEST}))
    assert first[-1]["type"] == "done"
    with Session(get_engine()) as session:
        task = session.get(ConversationTask, cid)
        assert task is not None and task.kind == "read_bundle"
        assert task.status == "needs_account"
        assert task.month == "2026-10"
        account_id = session.exec(select(Account)).first().id

    second = events(client.post(endpoint, headers=auth_headers, json={
        "content": "继续", "references": [{"kind": "account", "id": account_id}],
    }))
    assert second[-1]["type"] == "done"
    assert "三个只读查询目标均已取得可信结果" in second[-1]["message"]["content"]
    assert any(item["type"] == "bill_result" for item in second)
    assert "read_goal_coverage" not in [item["type"] for item in second]
    with Session(get_engine()) as session:
        assert session.get(ConversationTask, cid).status == "completed"


def test_bundle_task_cannot_finish_when_only_bill_is_verified(
    client, auth_headers, monkeypatch,
):
    from sqlmodel import Session, select
    from app.db.session import get_engine
    from app.models import ConversationTask, Account

    class Model:
        mode = "openai"
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            latest = str(messages[-1].get("content") or "")
            if tools is None:
                yield LLMChunk(content=json.dumps({"question": "请先选择账户"}, ensure_ascii=False))
            elif "服务端保存的未完成只读目标" in latest:
                yield LLMChunk(tool_calls=[call("get_monthly_bill", 31)])
            else:
                yield LLMChunk(content="三个目标已经全部完成。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    endpoint = f"/api/chat/conversations/{cid}/messages"
    events(client.post(endpoint, headers=auth_headers, json={"content": REQUEST}))
    with Session(get_engine()) as session:
        account_id = session.exec(select(Account)).first().id
    second = events(client.post(endpoint, headers=auth_headers, json={
        "content": "继续", "references": [{"kind": "account", "id": account_id}],
    }))
    assert second[-1]["type"] == "done"
    assert "尚未完成全部请求" in second[-1]["message"]["content"]
    with Session(get_engine()) as session:
        task = session.get(ConversationTask, cid)
        assert task.status == "needs_account"

def test_explicit_month_is_required_for_verified_bill_coverage():
    plan = build_read_goal_plan(REQUEST)
    assert plan.expected_month == "2026-10"
    assert build_read_goal_plan(REQUEST.replace("2026-10", "2026年10月")).expected_month == "2026-10"
    assert build_read_goal_plan(REQUEST.replace("2026-10", "2026/10")).expected_month == "2026-10"
    assert build_read_goal_plan("查2026-10和2026-09的账单、最近交易流水和订阅") is None
    assert build_read_goal_plan("查2026-10和2026-10的账单、最近交易流水和订阅") is None
    from datetime import timedelta, timezone
    from app.core.time import utcnow
    local_date = utcnow().astimezone(timezone(timedelta(hours=8)))
    last_month = local_date.replace(day=1) - timedelta(days=1)
    assert build_read_goal_plan(REQUEST.replace("2026-10", "本月")).expected_month == local_date.strftime("%Y-%m")
    assert build_read_goal_plan(REQUEST.replace("2026-10", "上个月")).expected_month == last_month.strftime("%Y-%m")
    for ambiguous in ("本月和上个月", "下个月", "近两个月", "最近三个月"):
        assert build_read_goal_plan(REQUEST.replace("2026-10", ambiguous)) is None
    assert build_read_goal_plan(REQUEST.replace("2026-10", "本月2026-10")) is None
    from app.services.conversation_tasks import ReadGoal, classify_pending_read_goal
    assert classify_pending_read_goal(REQUEST.replace("2026-10", "上个月")) == ReadGoal(
        "read_bundle", last_month.strftime("%Y-%m"))
    assert classify_pending_read_goal(REQUEST.replace("2026-10", "本月")) == ReadGoal(
        "read_bundle", local_date.strftime("%Y-%m"))
    assert classify_pending_read_goal(REQUEST.replace("2026-10", "本月和上个月")) is None
    assert classify_pending_read_goal("帮我查2026-09和2026-10的账单") is None

    wrong = ("get_monthly_bill", {"ok": True, "data": bill("2026-09", 12000, 6000)})
    transactions = ("list_recent_transactions", {"ok": True, "data": []})
    subscriptions = ("detect_subscriptions", {"ok": True, "data": []})
    results = [wrong, transactions, subscriptions]
    assert plan.verified(results) == ("list_recent_transactions", "detect_subscriptions")
    assert plan.next_unattempted(results) is None
    summary = plan.report(results)
    assert "尚未完成全部请求" in summary
    assert "月度账单：未取得可信结果" in summary
    assert "三个只读查询目标均已取得可信结果" not in summary


def test_wrong_month_tool_cannot_mark_three_goal_chat_complete(client, auth_headers, monkeypatch):
    class Model:
        mode = "openai"
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                first = call("get_monthly_bill", 101)
                first["function"]["arguments"] = '{"month":"2026-09"}'
                yield LLMChunk(tool_calls=[
                    first,
                    call("list_recent_transactions", 102),
                    call("detect_subscriptions", 103),
                ])
            else:
                yield LLMChunk(content="已完成所有查询。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    frames = events(client.post(
        f"/api/chat/conversations/{cid}/messages", headers=auth_headers,
        json={"content": REQUEST},
    ))
    assert frames[-1]["type"] == "done"
    assert any(frame["type"] == "bill_result" and frame["data"]["month"] == "2026-09"
               for frame in frames)
    content = frames[-1]["message"]["content"]
    assert "月度账单：未取得可信结果" in content
    assert "尚未完成全部请求" in content
    assert "均已取得可信结果" not in content
    assert model.calls <= 3

def test_verified_account_selection_scopes_balance_and_recent_transactions(
    client, auth_headers, monkeypatch,
):
    """Two owned accounts: model-supplied scope must not override selected account."""
    from sqlmodel import Session, select
    from app.db.session import get_engine
    from app.models import Account
    from app.services.vault import create_account_token

    with Session(get_engine()) as db:
        first = db.exec(select(Account)).first()
        second = Account(
            user_id=first.user_id, name="本轮选中的第二个模拟账户",
            masked_number="**** 9673", status="active", currency="CNY",
            balance_fen=246800,
        )
        db.add(second); db.flush()
        other_token = create_account_token(db, first.user_id, first.id)
        selected_id = second.id
        db.commit()

    class Model:
        tool_observations = None
        async def stream(self, messages, tools=None):
            if not any(m.get("role") == "tool" for m in messages):
                yield LLMChunk(tool_calls=[
                    {"id": "scope_balance", "type": "function",
                     "function": {"name": "get_account_balance",
                                  "arguments": json.dumps({"account_token": other_token})}},
                    {"id": "scope_transactions", "type": "function",
                     "function": {"name": "list_recent_transactions",
                                  "arguments": json.dumps({"account_token": other_token, "limit": 5})}},
                ])
            else:
                self.tool_observations = [json.loads(m["content"]) for m in messages
                                          if m.get("role") == "tool"]
                yield LLMChunk(content="查询结束。")

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    frames = events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": "查询我选中账户的余额和最近交易流水",
              "references": [{"kind": "account", "id": selected_id}]},
    ))
    assert frames[-1]["type"] == "done"
    assert model.tool_observations is not None
    balance, transactions = model.tool_observations
    assert balance["ok"] is True
    assert len(balance["data"]) == 1
    assert balance["data"][0]["name"] == "本轮选中的第二个模拟账户"
    assert balance["data"][0]["balance_fen"] == 246800
    assert transactions["ok"] is True
    assert transactions["data"] == []
    assert transactions["scope"]["kind"] == "single_account"
    assert "action_required" not in [event["type"] for event in frames]
