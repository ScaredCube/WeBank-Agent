"""Trusted comparison summary must not disclose amounts outside privacy-aware cards."""
from app.agent.financial_summary import summarize_bill_comparison


def result(month, consumption, *, account="活期", number="**** 0001", currency="CNY"):
    return ("get_monthly_bill", {"ok":True, "data":{
        "month":month, "consumption_fen":consumption,
        "account_name":account, "masked_number":number, "currency":currency,
    }})


def test_two_month_comparison_is_tool_based_and_has_no_amounts():
    summary=summarize_bill_comparison([
        result("2026-01",100000), result("2025-12",50000),
    ])
    assert summary is not None
    assert "2026-01" in summary and "2025-12" in summary
    assert "增加" in summary
    assert "500" not in summary and "1000" not in summary and "¥" not in summary


def test_spending_down_or_equal():
    assert "减少" in summarize_bill_comparison([
        result("2025-12",9000),result("2026-01",100),
    ])
    assert "持平" in summarize_bill_comparison([
        result("2025-12",0),result("2026-01",0),
    ])


def test_different_accounts_or_only_one_bill_do_not_create_false_comparison():
    assert summarize_bill_comparison([
        result("2025-12",20),result("2026-01",40,number="**** 0002"),
    ]) is None
    assert summarize_bill_comparison([result("2026-01",200)]) is None
    assert summarize_bill_comparison([
        result("2026-01",200),result("2026-01",400),
    ]) is None
    assert summarize_bill_comparison([
        result("2025-12",20),result("2026-01",40,currency="USD"),
    ]) is None
