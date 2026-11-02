"""Conservative goal-coverage check for one unattempted read-only query.

This module only suggests one remaining safe read to the model. It never
produces user-visible text and never claims that a goal is complete.
"""
from __future__ import annotations

from typing import Any
import re

_TRANSACTION_TOOL = "list_recent_transactions"
_DETECTION_TOOL = "detect_subscriptions"
_SUPPORTED = frozenset({_TRANSACTION_TOOL, _DETECTION_TOOL})
_TRANSACTION_CUES = ("交易", "流水", "明细", "收支记录")
_SUBSCRIPTION_CUES = ("订阅", "周期扣费", "自动续费", "自动扣费", "重复扣", "重复支付")
_SKIP_DETECTION = re.compile(
    r"(?:无需|不用|不要|别|不必|不需要).{0,6}"
    r"(?:查|看|识别|检测|检查|排查|核对).{0,10}"
    r"(?:订阅|自动扣费|周期扣费|重复扣费|重复支付)"
    r"|(?:只|仅)(?:需|要)?(?:看|查|查询).{0,8}(?:交易|流水)"
    r"|(?:不需要|不用|不要|不必|无需|无须|暂不).{0,5}(?:订阅|自动扣费|周期扣费)"
    r"|订阅.{0,4}(?:不用|不要|下次|以后|暂不)"
)


def _valid_rows(name: str, result: dict[str, Any]) -> list[dict] | None:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return None
    items = result.get("data")
    limit = 50 if name == _TRANSACTION_TOOL else 10
    if not isinstance(items, list) or len(items) > limit:
        return None
    if name == _TRANSACTION_TOOL:
        if not all(
            isinstance(item, dict)
            and item.get("direction") in {"income", "expense"}
            and type(item.get("amount_fen")) is int
            and item["amount_fen"] >= 0
            for item in items
        ):
            return None
    else:
        if not all(
            isinstance(item, dict)
            and isinstance(item.get("merchant"), str)
            and type(item.get("occurrences")) is int
            and item["occurrences"] >= 2
            and type(item.get("amount_fen")) is int
            and item["amount_fen"] >= 0
            for item in items
        ):
            return None
    return items


def _requests_transaction_and_subscription(user_request: str) -> bool:
    return (
        any(cue in user_request for cue in _TRANSACTION_CUES)
        and any(cue in user_request for cue in _SUBSCRIPTION_CUES)
        and not _SKIP_DETECTION.search(user_request)
    )


def missing_read_goal_for_retry(
    results: list[tuple[str, dict]], *, user_request: str,
) -> str | None:
    """Find one unattempted, explicit, low-risk read goal.

    Do not retry a failed tool, extend a mixed/action task, or guess from
    model-authored prose. An empty successful result counts as completed.
    """
    if (len(results) != 1 or any(action in user_request for action in (
        "取消", "退订", "关闭", "转账", "汇款", "打款", "申购", "赎回",
        "挂失", "冻结", "购买", "支付", "账单", "余额",
        "卡片状态", "银行卡状态", "理财", "持仓", "风险测评",
    ))):
        return None
    if not _requests_transaction_and_subscription(user_request):
        return None
    done, result = results[0]
    if done not in _SUPPORTED or _valid_rows(done, result) is None:
        return None
    return (_DETECTION_TOOL if done == _TRANSACTION_TOOL else _TRANSACTION_TOOL)
