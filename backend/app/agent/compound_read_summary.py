"""Grounded final summary for completed and partially completed read-only goals.

We never summarize model-authored findings as bank facts. The transaction list
and periodic-payment detector are two different evidence sources: the latter
does not prove duplicate subscriptions, double charges, or fraud.
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


def summarize_transaction_subscription_review(
    results: list[tuple[str, dict]], *, user_request: str,
) -> str | None:
    """Only describe what has been verified; call out an explicitly missing goal.

    Return None for other tool combinations or ordinary single-goal requests,
    preserving the established presentation path.
    """
    if not results or any(name not in _SUPPORTED for name, _ in results):
        return None
    requested_both = _requests_transaction_and_subscription(user_request)
    observed = {name for name, _ in results}
    if not requested_both and observed != _SUPPORTED:
        return None

    # Repeated/malformed responses should not create a misleading "complete"
    # verdict. The first successful, well-formed observation is authoritative.
    verified: dict[str, list[dict]] = {}
    for name, result in results:
        rows = _valid_rows(name, result)
        if rows is not None and name not in verified:
            verified[name] = rows

    descriptions: list[str] = []
    transactions = verified.get(_TRANSACTION_TOOL)
    detection = verified.get(_DETECTION_TOOL)
    if transactions is not None and detection is not None:
        # Only server-issued Tool observations can establish query scope;
        # never infer that the latest transaction list and the rolling
        # detector scanned the same financial records.
        tx_scope = next(
            (result.get("scope") for name, result in results
             if name == _TRANSACTION_TOOL and _valid_rows(name, result) is not None),
            None,
        )
        detect_scope = next(
            (result.get("scope") for name, result in results
             if name == _DETECTION_TOOL and _valid_rows(name, result) is not None),
            None,
        )
        if (isinstance(tx_scope, dict) and tx_scope.get("kind") == "single_account"
                and type(tx_scope.get("max_rows")) is int
                and 1 <= tx_scope["max_rows"] <= 50
                and isinstance(detect_scope, dict)
                and detect_scope.get("kind") == "all_user_accounts"
                and detect_scope.get("lookback_days") == 186):
            descriptions.append(
                "查询范围说明：最近交易来自单个模拟账户的有限条记录；"
                "疑似周期性扣费识别覆盖本人所有模拟账户近186天的支出流水。"
                "两者并非相同的交易样本，不能直接逐笔对应。"
            )
        else:
            descriptions.append(
                "本轮无法核验两个查询的账户与时间范围是否完全一致，"
                "不能直接把疑似订阅线索归因到本次交易列表。"
            )
    if transactions is not None:
        descriptions.append(f"最近交易查询本次返回 {len(transactions)} 笔记录。")
    elif requested_both:
        descriptions.append("本轮尚未取得可核验的最近交易列表。")

    if detection is not None:
        if detection:
            descriptions.append(
                f"从近186天的支出流水中识别到 {len(detection)} 项疑似周期性扣费线索。"
            )
        else:
            descriptions.append("本轮未从近186天的支出流水中识别到疑似周期性扣费线索。")
    elif requested_both:
        descriptions.append("本轮尚未完成可核验的周期性扣费识别。")

    if not descriptions:
        return None
    descriptions.append(
        "同一商户、同一金额跨月份出现，只能提示可能的订阅扣费；"
        "不能单凭这些记录认定存在重复订阅或异常扣费。"
        "建议对照订阅清单及扣费日期核实。"
    )
    if any(term in user_request for term in ("取消", "退订", "关闭订阅")):
        descriptions.append("当前结果仅包含查询与识别，不代表已经取消任何订阅。")
    return "".join(descriptions)
