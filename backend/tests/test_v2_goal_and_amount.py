"""Small V2 coverage / structured intent contract tests."""
from app.agent.goal_completion import missing_bill_goal
from app.risk.transfer_intent import requested_intent_amount_fen, requested_amount_fen


def test_balance_does_not_satisfy_explicit_bill_analysis_goal():
    prior = [("get_account_balance", {"ok": True, "data": []})]
    assert missing_bill_goal(prior, user_request="分析演示活期账户本月收支") == "get_monthly_bill"
    assert missing_bill_goal(prior, user_request="查询余额") is None
    assert missing_bill_goal(prior + [("get_monthly_bill", {"ok": True})],
                             user_request="分析本月收支") is None
    assert missing_bill_goal(prior, user_request="帮我转账并查账单") is None


def test_verified_cny_drag_field_allows_plain_number_but_chat_does_not():
    assert requested_intent_amount_fen("转换金额：1000") == 100000
    assert requested_intent_amount_fen("转换金额：1000元") == 100000
    assert requested_intent_amount_fen("转换金额：1000.25") == 100025
    assert requested_intent_amount_fen("转换金额：1000元及其他操作") is None
    assert requested_intent_amount_fen("转换金额：-1000") is None
    assert requested_intent_amount_fen("转换金额：1000.999") is None
    assert requested_amount_fen("转换金额：1000") is None
