"""Deterministic narration of multiple trusted monthly bill tool results.

Amounts in this text must originate from validated Tool data, never the model.
"""
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
        if not isinstance(month, str) or type(amount) is not int or amount < 0:
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
    # Keep raw amounts only inside privacy-aware financial cards.
    # The short, Tool-derived qualitative comparison avoids duplicate sensitive
    # figures in the assistant prose and cannot be authored by the model.
    direction = "增加" if new_amount > old_amount else "减少" if new_amount < old_amount else "持平"
    return f"{second_month} 的消费较 {first_month} {direction}。两个月的账单明细见下方。"
