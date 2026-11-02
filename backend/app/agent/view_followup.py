"""Bounded presentation of server-verified view selections."""
from typing import Any

from app.agent.response_policy import NoToolScope, classify_no_tool_request

_EXTRA_READ_CUES = (
    "查询", "查一下", "查查", "看看", "看一下", "显示", "列出", "明细", "流水",
    "余额", "上个月", "其他月份", "相比", "比较", "对比", "趋势", "顺便", "另外",
)


def render_view_followup(question: str, selection: dict[str, Any] | None) -> str | None:
    if (not selection
            or classify_no_tool_request(question) in {NoToolScope.ACTION, NoToolScope.ACTION_STATUS}
            or any(cue in question for cue in _EXTRA_READ_CUES)):
        return None
    if not any(cue in question for cue in ("分类", "这项", "这类", "这个", "为什么", "值得注意", "这么多")):
        return None
    label = selection.get("selected_category")
    amount = selection.get("selected_category_amount_fen")
    count = selection.get("selected_category_count")
    month = selection.get("selected_category_month")
    if not isinstance(label, str) or type(amount) is not int or amount < 0 or type(count) is not int or count < 0 or not isinstance(month, str):
        return None
    whole, cents = divmod(amount, 100)
    return (f"{month} 的{label}消费共 {whole:,}.{cents:02d} 元，涉及 {count} 笔。"
            "仅凭分类汇总无法判断花费较多的原因；可以结合交易明细或其他月份继续分析。")
