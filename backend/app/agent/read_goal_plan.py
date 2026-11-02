"""Evidence-based execution plan for explicit three-part read-only requests.

This module only evaluates trusted Tool observations. The model still proposes
Tool calls, and ToolExecutor remains the sole authorization boundary. Plans
never initiate payments or authorize reuse of previous account selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.agent.compound_read_summary import _valid_rows
from app.schemas.bills import MonthlyBill
from app.tools.presentation import render_tool_result

_GOALS = ("get_monthly_bill", "list_recent_transactions", "detect_subscriptions")
_LABELS = {
    "get_monthly_bill": "月度账单",
    "list_recent_transactions": "最近交易流水",
    "detect_subscriptions": "疑似周期性扣费识别",
}
_BILL = ("账单", "收支")
_TRANSACTION = ("最近交易", "交易流水", "最近流水", "交易明细", "流水记录")
_SUBSCRIPTION = ("订阅", "自动续费", "周期扣费", "自动扣费", "重复扣费", "重复订阅")
_ACTION = (
    "转账", "汇款", "打款", "付款", "支付", "申购", "赎回",
    "取消", "退订", "挂失", "冻结", "购买", "转换", "转给",
    "操作成功", "执行", "提交订单",
)
_SKIP = ("不要", "不用", "无需", "不必", "别查", "暂不", "只查", "仅查")
_ALLOWED_EXTRA = frozenset()  # Don't broaden a three-part request by inferred goals.


def _trusted(name: str, result: dict[str, Any]) -> bool:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    if name == "get_monthly_bill":
        try:
            MonthlyBill.model_validate(result.get("data"))
            return True
        except (ValidationError, TypeError, ValueError):
            return False
    if name in ("list_recent_transactions", "detect_subscriptions"):
        return _valid_rows(name, result) is not None
    return False


@dataclass(frozen=True)
class ReadGoalPlan:
    """Fixed ordered set of read-only goals; no tool arguments or auth tokens."""

    goals: tuple[str, ...] = _GOALS

    def verified(self, results: list[tuple[str, dict]]) -> tuple[str, ...]:
        return tuple(goal for goal in self.goals
                     if any(name == goal and _trusted(name, res)
                            for name, res in results))

    def next_unattempted(self, results: list[tuple[str, dict]]) -> str | None:
        if not results or any(
            name not in self.goals and name not in _ALLOWED_EXTRA
            or not _trusted(name, result)
            for name, result in results
        ):
            return None
        seen = {name for name, _ in results}
        return next((goal for goal in self.goals if goal not in seen), None)

    def report(self, results: list[tuple[str, dict]]) -> str | None:
        if any(name not in self.goals for name, _ in results):
            return None
        valid = {name: res for name, res in results
                 if name in self.goals and _trusted(name, res)}
        if not valid:
            return None
        finished = [goal for goal in self.goals if goal in valid]
        missing = [goal for goal in self.goals if goal not in valid]
        if missing:
            intro = "本轮已取得部分可信查询结果，尚未完成全部请求。"
        else:
            intro = "本轮三个只读查询目标均已取得可信结果。"
        descriptions: list[str] = [intro]
        for goal in self.goals:
            if goal not in valid:
                descriptions.append(f"{_LABELS[goal]}：未取得可信结果。")
                continue
            data = valid[goal]["data"]
            if goal == "get_monthly_bill":
                descriptions.append(f"月度账单：{data['month']} 已核验，收支详情见账单卡。")
            elif goal == "list_recent_transactions":
                descriptions.append(f"最近交易流水：本轮返回 {len(data)} 笔记录。")
            else:
                descriptions.append(
                    f"疑似周期性扣费识别：本轮得到 {len(data)} 项线索，"
                    "不代表已确认重复扣费或完成任何取消操作。"
                )
        descriptions.append(
            "月度账单、最近交易列表和周期扣费识别可能具有不同的时间及账户范围，"
            "不能将三者视作逐笔一致的样本。"
        )
        for goal in finished:
            if goal != "get_monthly_bill":
                try:
                    detail = render_tool_result(goal, valid[goal])
                except (ValueError, TypeError, IndexError, KeyError):
                    detail = ""
                if detail:
                    descriptions.append(detail)
        return "\n\n".join(descriptions)


def build_read_goal_plan(request: str) -> ReadGoalPlan | None:
    """Only an unambiguous user-requested bill + transactions + subscriptions.

    Refuse action requests, negations, large untrusted text, and underspecified
    two-goal queries; existing dedicated handlers retain their established paths.
    """
    if not isinstance(request, str) or not 8 <= len(request) <= 500:
        return None
    if any(term in request for term in _ACTION + _SKIP):
        return None
    if not (any(term in request for term in _BILL)
            and any(term in request for term in _TRANSACTION)
            and any(term in request for term in _SUBSCRIPTION)):
        return None
    return ReadGoalPlan()
