"""Render banking data from trusted tool results, never model-authored figures."""


def _money(fen: int) -> str:
    return f"{fen // 100:,}.{fen % 100:02d}"


def render_tool_result(name: str, result: dict) -> str:
    if not result["ok"]:
        return f"查询未完成：{result['error']}。"
    data = result["data"]
    if name == "get_account_balance":
        if not data:
            return "未找到模拟账户。"
        return "\n\n".join(
            f"{item['name']}（{item['masked_number']}）\n可用余额：{_money(item['balance_fen'])} 元"
            for item in data
        )
    if name == "list_recent_transactions":
        if not data:
            return "没有查询到模拟交易记录。"
        lines = ["模拟交易记录："]
        for item in data:
            direction = "收入" if item["direction"] == "income" else "支出"
            lines.append(f"- {item['occurred_at'][:10]} {direction} {_money(item['amount_fen'])} 元"
                         f"，{item['category']}，{item['counterparty']}")
        return "\n".join(lines)
    return "查询未完成：工具不可用。"
