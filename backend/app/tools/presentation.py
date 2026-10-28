"""Render banking data from trusted tool results, never model-authored figures."""


def _money(fen: int) -> str:
    return f"{fen // 100:,}.{fen % 100:02d}"


def _rate(bps: int) -> str:
    return f"{bps // 100}.{bps % 100:02d}%"


def render_tool_result(name: str, result: dict) -> str:
    if not result["ok"]:
        if name == "calculate":
            return f"计算未完成：{result['error']}。"
        if name == "prepare_transfer":
            return f"模拟转账未准备：{result['error']}。"
        if name == "prepare_card_loss":
            return f"模拟挂失未准备：{result['error']}。"
        if name == "prepare_wealth_subscribe":
            return f"理财申购未准备：{result['error']}。"
        if name == "prepare_wealth_redeem":
            return f"理财赎回未准备：{result['error']}。"
        if name == "prepare_cancel_subscription":
            return f"取消订阅未准备：{result['error']}。"
        return f"查询未完成：{result['error']}。"
    data = result["data"]
    if name == "get_card_status":
        if not data:
            return "未找到模拟卡片。"
        card_status = {"active": "正常", "lost": "已挂失"}
        account_status = {"active": "正常", "frozen": "已冻结"}
        return "\n".join(f"{item['account_name']}（{item['masked_number']}）：卡片状态：{card_status.get(item['status'], '不可用')}；账户状态：{account_status.get(item['account_status'], '不可用')}"
                         for item in data)
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
    if name == "calculate":
        value = data.get("result") if isinstance(data, dict) else None
        if type(value) is int:
            return f"计算结果：{value:,}"
        if type(value) is float:
            return f"计算结果：{value:.12g}"
        return "计算未完成。"
    if name == "get_wealth_products":
        if not data:
            return "暂无可申购的模拟理财产品。"
        lines = ["模拟理财产品："]
        for item in data:
            term = f"期限 {item['term_days']} 天" if item["term_days"] else "随时可赎回"
            lines.append(f"- {item['name']}：风险 {item['risk_level']}，"
                         f"参考年化 {_rate(item['expected_rate_bps'])}，"
                         f"起购 {_money(item['min_amount_fen'])} 元，{term}")
        return "\n".join(lines)
    if name == "get_wealth_holdings":
        if not data:
            return "暂无模拟理财持仓。"
        lines = ["模拟理财持仓："]
        for item in data:
            lines.append(f"- {item['product_name']}：持仓 {_money(item['amount_fen'])} 元，"
                         f"昨日收益 {_money(item['yesterday_earnings_fen'])} 元")
        return "\n".join(lines)
    if name == "get_subscriptions":
        if not data:
            return "没有查询到模拟订阅。"
        cycle = {"monthly": "每月", "quarterly": "每季度", "yearly": "每年"}
        lines = ["模拟订阅："]
        for item in data:
            status = "已取消" if item["status"] == "cancelled" else "生效中"
            soon = "，即将续费" if item["renewal_soon"] else ""
            lines.append(f"- {item['merchant']}：{_money(item['amount_fen'])} 元，"
                         f"{cycle.get(item['cycle'], item['cycle'])}，下次扣费 {item['next_charge_date']}，"
                         f"还有 {item['days_until_charge']} 天{soon}，状态：{status}")
        return "\n".join(lines)
    if name == "detect_subscriptions":
        if not data:
            return "未从最近模拟流水中识别到可能的重复订阅。"
        lines = ["可能存在的订阅："]
        for item in data:
            lines.append(f"- {item['merchant']}：{_money(item['amount_fen'])} 元，"
                         f"出现 {item['occurrences']} 次，最近一次 {item['last_occurred_at'][:10]}")
        return "\n".join(lines)
    if name == "get_wealth_risk_profile":
        if data.get("risk_level") == "未评估":
            return "尚未完成模拟理财风险测评。"
        return f"模拟理财风险等级：{data['risk_level']}；测评分数：{data['score']}/9。"
    if name == "get_monthly_bill":
        lines = [f"{data['month']} 月度账单（北京时间）",
                 f"{data['account_name']}（{data['masked_number']}）",
                 f"总收入：{_money(data['income_fen'])} 元；总支出：{_money(data['expense_fen'])} 元",
                 f"消费：{_money(data['consumption_fen'])} 元，共 {data['consumption_count']} 笔",
                 f"转出：{_money(data['transfer_out_fen'])} 元，共 {data['transfer_out_count']} 笔；转入：{_money(data['transfer_in_fen'])} 元，共 {data['transfer_in_count']} 笔"]
        for category in data["categories"]:
            lines.append(f"- {category['category']}：{_money(category['amount_fen'])} 元，{category['count']} 笔")
        for anomaly in data["anomalies"]:
            lines.append(f"需核对：{anomaly['reason']}，{anomaly['counterparty']}，{_money(anomaly['amount_fen'])} 元，{anomaly['previous_occurred_at']} / {anomaly['occurred_at']}")
        if data["ignored_count"]:
            lines.append(f"另有 {data['ignored_count']} 笔方向不明的流水未计入统计。")
        return "\n".join(lines)
    return "查询未完成：工具不可用。"
