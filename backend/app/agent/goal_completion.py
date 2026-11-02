"""Narrow V2 goal coverage checks; only suggest an unattempted safe read.

The Agent, not this module, must select the next call. No write or execution
may ever be auto-retried because an objective is incomplete.
"""
from __future__ import annotations

from typing import Any

_BILL_GOAL = ("账单", "收支", "消费", "本月支出", "本月收入", "月度分析")
_ACTION_GOAL = (
    "转账", "汇款", "支付", "付款", "申购", "赎回", "挂失",
    "冻结", "取消订阅", "办理", "执行", "确认", "转换", "购买",
)
_SAFE_PRIOR = frozenset({
    "get_account_balance", "get_card_status", "get_monthly_bill",
    "get_wealth_holdings", "get_wealth_products", "list_recent_transactions",
})


def missing_bill_goal(
    results: list[tuple[str, dict[str, Any]]], *, user_request: str
) -> str | None:
    """Return one missing bill Tool name only after a valid earlier read.

    This does not claim that a mere balance lookup completes a user-requested
    income/expense analysis. The tool executor still validates ownership.
    """
    if (not user_request or not any(cue in user_request for cue in _BILL_GOAL)
            or any(cue in user_request for cue in _ACTION_GOAL)
            or not results
            or any(name not in _SAFE_PRIOR or not isinstance(result, dict)
                   or result.get("ok") is not True for name, result in results)
            or any(name == "get_monthly_bill" for name, _ in results)):
        return None
    return "get_monthly_bill"
