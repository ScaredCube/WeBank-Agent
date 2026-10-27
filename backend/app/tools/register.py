from app.agent.registry import RiskLevel, ToolRegistry, ToolSpec
from app.tools.account_tools import (
    BalanceArguments, TransactionArguments, get_account_balance, list_recent_transactions,
)


def create_readonly_registry() -> ToolRegistry:
    """Build the explicitly permitted read-only tool registry."""
    result = ToolRegistry()
    for name, description, args, handler in (
        ("get_account_balance", "查询当前用户的模拟账户余额", BalanceArguments, get_account_balance),
        ("list_recent_transactions", "查询当前用户模拟账户的最近交易", TransactionArguments, list_recent_transactions),
    ):
        result.register(ToolSpec(name=name, description=description, parameters=args.model_json_schema(),
                                 risk=RiskLevel.GREEN, handler=handler))
    return result
