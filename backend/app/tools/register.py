from app.agent.registry import RiskLevel, ToolRegistry, ToolSpec
from app.tools.account_tools import (
    BalanceArguments, TransactionArguments, get_account_balance, list_recent_transactions,
)
from app.tools.transfer_tools import TransferArguments, prepare_transfer_tool
from app.tools.bill_tools import MonthlyBillArguments, get_monthly_bill
from app.tools.calculator_tools import CalculateArguments, calculate
from app.tools.card_tools import CardArguments, get_card_status, prepare_card_loss
from app.tools.wealth_tools import (
    WealthHoldingArguments, WealthPrepareArguments, WealthProductArguments, WealthRiskArguments,
    get_wealth_holdings, get_wealth_products, get_wealth_risk_profile,
    prepare_wealth_redeem, prepare_wealth_subscribe,
)
from app.tools.subscription_tools import (
    SubscriptionArguments, SubscriptionCancelArguments, detect_subscriptions,
    get_subscriptions, prepare_cancel_subscription,
)


def create_readonly_registry() -> ToolRegistry:
    """Build the explicitly permitted read-only tool registry."""
    result = ToolRegistry()
    for name, description, args, handler in (
        ("get_account_balance", "查询当前用户的模拟账户余额", BalanceArguments, get_account_balance),
        ("list_recent_transactions", "查询当前用户模拟账户的最近交易", TransactionArguments, list_recent_transactions),
        ("get_monthly_bill", "分析当前用户模拟账户的月度收支、消费分类及需核对的重复消费；month 格式 YYYY-MM，省略为北京时间当月", MonthlyBillArguments, get_monthly_bill),
        ("get_card_status", "查询本人模拟卡片状态", CardArguments, get_card_status),
        ("get_wealth_products", "查询可申购的模拟理财产品及参考年化、风险等级和起购金额", WealthProductArguments, get_wealth_products),
        ("get_wealth_holdings", "查询本人模拟理财持仓和昨日收益", WealthHoldingArguments, get_wealth_holdings),
        ("get_wealth_risk_profile", "查询本人模拟理财风险测评等级", WealthRiskArguments, get_wealth_risk_profile),
        ("get_subscriptions", "查询本人模拟订阅、下次扣费日期和续费提醒", SubscriptionArguments, get_subscriptions),
        ("detect_subscriptions", "从最近模拟消费流水中识别可能的重复订阅", SubscriptionArguments, detect_subscriptions),
    ):
        result.register(ToolSpec(name=name, description=description, parameters=args.model_json_schema(),
                                 risk=RiskLevel.GREEN, handler=handler))
    return result


def create_agent_registry() -> ToolRegistry:
    registry = create_readonly_registry()
    registry.register(ToolSpec(
        name="calculate",
        description="执行受限纯数学计算；仅支持数字、括号和 + - * / // % **，不执行变量、函数、属性或代码",
        parameters=CalculateArguments.model_json_schema(), risk=RiskLevel.GREEN, handler=calculate,
    ))
    registry.register(ToolSpec(
        name="prepare_transfer", description="准备模拟转账，等待用户确认或演示验证，不会直接执行或扣款",
        parameters=TransferArguments.model_json_schema(), risk=RiskLevel.YELLOW,
        handler=prepare_transfer_tool,
    ))
    registry.register(ToolSpec(name="prepare_card_loss", description="准备模拟卡片挂失，必须由用户完成红色模拟验证后单独执行",
        parameters=CardArguments.model_json_schema(), risk=RiskLevel.RED, handler=prepare_card_loss))
    registry.register(ToolSpec(name="prepare_wealth_subscribe", description="准备模拟理财申购，必须由用户完成红色模拟验证后单独执行",
        parameters=WealthPrepareArguments.model_json_schema(), risk=RiskLevel.RED, handler=prepare_wealth_subscribe))
    registry.register(ToolSpec(name="prepare_wealth_redeem", description="准备模拟理财赎回，必须由用户完成红色模拟验证后单独执行",
        parameters=WealthPrepareArguments.model_json_schema(), risk=RiskLevel.RED, handler=prepare_wealth_redeem))
    registry.register(ToolSpec(name="prepare_cancel_subscription", description="准备取消模拟订阅，等待用户确认后单独执行",
        parameters=SubscriptionCancelArguments.model_json_schema(), risk=RiskLevel.YELLOW,
        handler=prepare_cancel_subscription))
    return registry
