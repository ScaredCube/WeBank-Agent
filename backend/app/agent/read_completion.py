"""Conservative fast-path completion for *fully verified* simple read requests.

This is deliberately not a general intent parser or task planner. If a request
has any extra service, interpretation or action goal, keep the Agent running.
Never infer the original user request by splitting a model-visible context blob.
"""
import re

from app.agent.financial_summary import summarize_bill_comparison

_BILL_CUES = ("账单", "消费", "收支", "上个月", "下个月", "前一个月", "相比", "对比", "比较")
# A reference to a card is not necessarily a request to inspect its status.
_CARD_STATUS_CUES = (
    "银行卡状态", "卡片状态", "卡状态", "这张卡状态", "这张卡的状态",
    "银行卡是否正常", "卡片是否正常",
)
_COMPARE_CUES = ("上个月", "相比", "对比", "比较", "变化", "多了多少", "少了多少")
_MONTH_REFERENCES = re.compile(
    r"(?<!\d)(?:20\d{2}[-/](?:0[1-9]|1[0-2])|(?:20\d{2}年)?(?:0?[1-9]|1[0-2])月)"
)

# Ambiguous or compound goals must go through the model/tool loop. A false
# negative costs a model round; a false positive silently drops user intent.
_OTHER_GOALS = (
    "转账", "汇款", "打款", "挂失", "冻结", "申购", "赎回", "收款",
    "取消", "订阅", "重复扣费", "重复消费", "自动扣款",
    "余额", "交易", "流水",
    "理财", "持仓", "风险测评", "产品",
    "计算", "算出", "算一下", "手续费", "利息",
    "逐笔", "每笔", "异常", "识别",
    "为什么", "原因", "解释", "建议", "推荐", "预测", "趋势",
    "怎么办", "怎么回事", "如何处理", "查找", "排查",
    "近三个月", "最近三个月", "过去三个月", "连续三个月",
    "所有月份", "每个月", "半年", "一年账单",
    "然后", "顺便", "接着", "另外", "还要", "再帮我", "并且",
)


def _original_request(history: list[dict], user_request: str | None) -> str | None:
    if user_request is not None:
        return user_request.strip()
    # Legacy direct callers do not have a separate request string. If this is
    # a decorated model message, fail closed rather than truncating at "\n\n[":
    # the user could have typed the same delimiter and a second instruction.
    latest = next((str(entry.get("content") or "") for entry in reversed(history)
                   if entry.get("role") == "user"), "")
    if "\n\n[" in latest:
        return None
    return latest.strip()


def completed_readonly_summary(
    history: list[dict],
    results: list[tuple[str, dict]],
    *,
    user_request: str | None = None,
) -> str | None:
    """Return a safe fast-path message or None to leave planning to the Agent."""
    if not results or any(
        tool not in {"get_monthly_bill", "get_card_status"} or not result.get("ok")
        for tool, result in results
    ):
        return None
    request = _original_request(history, user_request)
    if not request or any(cue in request for cue in _OTHER_GOALS):
        return None
    wants_categories = any(cue in request for cue in ("分类", "类别"))
    if wants_categories:
        # A monthly aggregate supports displaying category totals, not
        # transaction details, rankings, proportions or causal analysis.
        if any(cue in request for cue in ("占比", "比例", "排行", "排名", "最多", "最少",
                                           "最高", "最低", "明细", "详情", "筛选", "过滤",
                                           "只看", "仅看", "单独", "选中", "指定", "商户")):
            return None
        bills = [result.get("data") for tool, result in results if tool == "get_monthly_bill"]
        if not bills or any(
            not isinstance(data, dict) or not isinstance(data.get("categories"), list)
            or any(not isinstance(row, dict) or not isinstance(row.get("category"), str)
                   or type(row.get("amount_fen")) is not int or row["amount_fen"] < 0
                   or type(row.get("count")) is not int or row["count"] < 0
                   for row in data["categories"])
            for data in bills
        ):
            return None
    # Two explicitly named months require more evidence than one result card.
    # Keep such requests in the normal model loop, regardless of punctuation.
    if len(_MONTH_REFERENCES.findall(request)) > 1:
        return None

    wants_bill = any(cue in request for cue in _BILL_CUES)
    wants_card = any(cue in request for cue in _CARD_STATUS_CUES)
    if not wants_bill and not wants_card:
        return None

    names = [name for name, _ in results]
    if wants_bill and "get_monthly_bill" not in names:
        return None
    if wants_card and "get_card_status" not in names:
        return None
    # A comparison is complete only if both validated month snapshots match
    # the same account; the helper enforces that evidence requirement.
    if wants_bill and any(cue in request for cue in _COMPARE_CUES):
        return summarize_bill_comparison(results)
    # Multi-month requests require additional evidence beyond one bill card.
    if wants_bill and any(cue in request for cue in ("两个月", "近两月", "最近两月", "过去两月", "两期")):
        return None
    if wants_bill and wants_card:
        return "银行卡状态和账单已查询，明细见下方结果卡。"
    if wants_bill:
        return ("账单已查询，消费分类汇总见下方结果卡。" if wants_categories
                else "账单已查询，明细见下方结果卡。")
    return "银行卡状态已查询，详见下方卡片。"
