"""End an already fulfilled READ-ONLY banking task without another model round.

This is deliberately narrow: trusted tool output is required and any request
for mutation, extra calculation, many months, or a different service continues
through the normal Agent/Guard path. No model-authored financial amounts.
"""
from app.agent.financial_summary import summarize_bill_comparison

_BILL_CUES = ("账单", "消费", "收支", "上个月", "下个月", "前一个月", "相比", "对比", "比较")
_CARD_CUES = ("银行卡", "卡片", "这张卡", "卡状态")
_COMPARE_CUES = ("上个月", "相比", "对比", "比较")
_UNSAFE_OR_COMPLEX = (
    "转账", "汇款", "打款", "挂失", "冻结", "申购", "赎回",
    "取消订阅", "计算", "算出", "算一下", "逐笔",
    "近三个月", "最近三个月", "所有月份", "每个月",
)


def completed_readonly_summary(history: list[dict], results: list[tuple[str, dict]]) -> str | None:
    if not results or any(tool not in {"get_monthly_bill", "get_card_status"} or not result.get("ok")
                          for tool, result in results):
        return None
    latest = next((str(entry.get("content") or "") for entry in reversed(history)
                   if entry.get("role") == "user"), "")
    request = latest.split("\n\n[", 1)[0]
    if any(cue in request for cue in _UNSAFE_OR_COMPLEX):
        return None
    wants_bill = any(cue in request for cue in _BILL_CUES)
    wants_card = any(cue in request for cue in _CARD_CUES)
    if not (wants_bill or wants_card):
        return None
    names = [tool for tool, _ in results]
    if wants_bill and "get_monthly_bill" not in names:
        return None
    if wants_card and "get_card_status" not in names:
        return None
    if wants_bill and any(cue in request for cue in _COMPARE_CUES):
        return summarize_bill_comparison(results)
    if wants_bill and wants_card:
        return "银行卡状态和账单已查询，明细见下方结果卡。"
    if wants_bill:
        return "账单已查询，明细见下方结果卡。"
    return "银行卡状态已查询，详见下方卡片。"
