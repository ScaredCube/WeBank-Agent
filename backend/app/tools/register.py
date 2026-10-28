from app.agent.registry import RiskLevel, ToolRegistry, ToolSpec
from app.tools.account_tools import (
    BalanceArguments, TransactionArguments, get_account_balance, list_recent_transactions,
)
from app.tools.transfer_tools import TransferArguments, prepare_transfer_tool
from app.tools.bill_tools import MonthlyBillArguments, get_monthly_bill


def create_readonly_registry() -> ToolRegistry:
    """Build the explicitly permitted read-only tool registry."""
    result = ToolRegistry()
    for name, description, args, handler in (
        ("get_account_balance", "查询当前用户的模拟账户余额", BalanceArguments, get_account_balance),
        ("list_recent_transactions", "查询当前用户模拟账户的最近交易", TransactionArguments, list_recent_transactions),
        ("get_monthly_bill", "分析当前用户模拟账户的月度收支、消费分类及需核对的重复消费；month 格式 YYYY-MM，省略为北京时间当月", MonthlyBillArguments, get_monthly_bill),
    ):
        result.register(ToolSpec(name=name, description=description, parameters=args.model_json_schema(),
                                 risk=RiskLevel.GREEN, handler=handler))
    return result


def create_agent_registry() -> ToolRegistry:
    registry = create_readonly_registry()
    registry.register(ToolSpec(
        name="prepare_transfer", description="准备模拟转账，等待用户确认或演示验证，不会直接执行或扣款",
        parameters=TransferArguments.model_json_schema(), risk=RiskLevel.YELLOW,
        handler=prepare_transfer_tool,
    ))
    return registry
