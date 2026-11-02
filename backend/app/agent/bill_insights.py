"""Conservative, deterministic insights about ONE verified monthly bill.

Only ranking of validated expenditure categories is expressed; a category
distribution cannot establish spending causes, investment returns, or fraud.
"""
from __future__ import annotations

from app.agent.financial_summary import _category_amounts


def summarize_bill_insights(results: list[tuple[str, dict]], user_request: str) -> str | None:
    if (len(results) != 1 or not any(cue in user_request for cue in
        ("分析", "消费结构", "分类分析", "消费分类"))
        or any(cue in user_request for cue in
        ("为什么", "原因", "增长", "增加", "上涨", "比较", "对比", "变化", "异常", "趋势"))):
        return None
    name, result = results[0]
    if name != "get_monthly_bill" or result.get("ok") is not True:
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    # A synthetic or customer-controlled string may contain sensitive data:
    # refuse all prose amplification rather than surface those fields.
    if any("[敏感号码已隐藏]" in str(data.get(k, "")) for k in
           ("account_name", "masked_number")):
        return None
    amounts = _category_amounts(data)
    if amounts is None:
        return None
    if not amounts or sum(amounts.values()) == 0:
        return ("本月账单没有可比较的消费分类金额。"
                "收入、转账和理财资金进出分别统计，不能等同于消费或投资收益。")
    ordered = sorted(((name, amount) for name, amount in amounts.items() if amount > 0),
                     key=lambda item: (-item[1], item[0]))
    lead = ordered[0][0]
    if len(ordered) == 1:
        text = f"按这份已核验账单的消费分类汇总，记录到的消费集中在{lead}。"
    else:
        second = ordered[1][0]
        text = f"按这份已核验账单的消费分类汇总，{lead}支出最高，其次是{second}。"
    text = "账单已查询。" + text
    text += ("这是账单分类结构，尚不能证明消费变化的原因。"
             "如需寻找具体支出，可继续查看相应月份的交易明细。")
    ignored = data.get("ignored_count")
    if type(ignored) is int and ignored > 0:
        text += "另有方向不明的流水未纳入统计。"
    return text
