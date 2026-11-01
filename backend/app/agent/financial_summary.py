"""Grounded and privacy-conscious comparison of two verified monthly bills.

A category difference is evidence about where consumption changed; it is not
proof of *why* the customer spent more. Figures stay in protected result cards.
"""
import re

_MONTH = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
_CATEGORY = re.compile(r"^(?:[\u4e00-\u9fff]{1,16}|[A-Za-z][A-Za-z _/\-]{0,20})$")


def _category_amounts(data: dict) -> dict[str, int] | None:
    rows = data.get("categories")
    consumption = data.get("consumption_fen")
    if not isinstance(rows, list) or type(consumption) is not int or consumption < 0:
        return None
    amounts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        category, amount = row.get("category"), row.get("amount_fen")
        if (not isinstance(category, str) or not _CATEGORY.fullmatch(category)
                or type(amount) is not int or amount < 0 or category in amounts):
            # Never surface arbitrary category text or infer partial-category causes.
            return None
        amounts[category] = amount
    if sum(amounts.values()) != consumption:
        return None
    return amounts


def incomplete_bill_comparison(results: list[tuple[str, dict]], request: str) -> str | None:
    """Do not mistake a single monthly bill for an explanation of growth."""
    if not any(term in request for term in (
        "为什么", "原因", "增加", "变多", "上涨", "变高", "上升",
        "相比", "对比", "比较", "差异", "变化",
    )):
        return None
    if not any(term in request for term in ("消费", "账单", "支出", "收支")):
        return None
    if not results or any(name != "get_monthly_bill" or not result.get("ok")
                          for name, result in results):
        return None
    months = {result.get("data", {}).get("month") for _, result in results
              if isinstance(result.get("data"), dict)}
    if len(months) != 1:
        return None
    return ("本轮只有一个月份的可信账单，无法据此判断消费是否增加，"
            "也不能确定增加的原因。可以指定一个对比月份继续查询；"
            "当前月份的明细见下方账单卡。")


def summarize_bill_comparison(results: list[tuple[str, dict]]) -> str | None:
    bills: dict[str, dict] = {}
    for tool, result in results:
        if tool != "get_monthly_bill" or not result.get("ok"):
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        month = data.get("month")
        amount = data.get("consumption_fen")
        if (not isinstance(month, str) or not _MONTH.fullmatch(month)
                or type(amount) is not int or amount < 0):
            continue
        if month in bills:
            continue
        bills[month] = data
    if len(bills) != 2:
        return None
    first_month, second_month = sorted(bills)
    old, new = bills[first_month], bills[second_month]
    if (not old.get("masked_number") or old.get("masked_number") != new.get("masked_number")
            or old.get("account_name") != new.get("account_name")
            or old.get("currency") != "CNY" or new.get("currency") != "CNY"):
        return None
    old_amount, new_amount = old["consumption_fen"], new["consumption_fen"]
    direction = "增加" if new_amount > old_amount else "减少" if new_amount < old_amount else "持平"
    headline = f"{second_month} 的消费较 {first_month} {direction}。"
    older, newer = _category_amounts(old), _category_amounts(new)
    if older is None or newer is None:
        return headline + "分类数据不足，无法确定主要变化来自哪里；两个月的明细见下方账单卡。"

    differences = {category: newer.get(category, 0) - older.get(category, 0)
                   for category in older.keys() | newer.keys()}
    if new_amount > old_amount:
        ranked = sorted(((category, delta) for category, delta in differences.items() if delta > 0),
                        key=lambda item: (-item[1], item[0]))
        category_note = (f"分类对比中，{ranked[0][0]}的支出增加最多。"
                         if ranked else "分类数据未显示单项支出增长，需核对账单。")
    elif new_amount < old_amount:
        ranked = sorted(((category, delta) for category, delta in differences.items() if delta < 0),
                        key=lambda item: (item[1], item[0]))
        category_note = (f"分类对比中，{ranked[0][0]}的支出减少最多。"
                         if ranked else "分类数据未显示单项支出下降，需核对账单。")
    else:
        category_note = ("虽然消费总额持平，分类支出结构发生了变化。"
                         if any(differences.values()) else "分类支出没有变化。")
    return (headline + category_note
            + "这只能说明支出分布变化，无法仅凭账单判断消费变化的实际原因；"
            "可结合对应月份的交易明细进一步核对。")
