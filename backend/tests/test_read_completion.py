"""Stop only fulfilled, verified read-only tasks; never shortcut complex tasks."""
from app.agent.read_completion import completed_readonly_summary


def bill(month, amount):
    return ("get_monthly_bill", {"ok":True, "data": {
        "month":month,"consumption_fen":amount,
        "account_name":"活期","masked_number":"**** 0001","currency":"CNY",
    }})


def card():
    return ("get_card_status", {"ok":True,"data": {"cards":[]}})


def history(text):
    return [{"role":"user","content":text}]


def test_single_bill_can_finish_after_one_successful_tool():
    output=completed_readonly_summary(history("请查询本月账单"),[bill("2026-01",1000)])
    assert output=="账单已查询，明细见下方结果卡。"


def test_joint_requires_both_results():
    assert completed_readonly_summary(history("查看银行卡状态和账单"),[bill("2026-01",1000)]) is None
    assert completed_readonly_summary(history("查看银行卡状态和账单"),[card(),bill("2026-01",1000)]) is not None


def test_comparison_requires_two_distinct_trusted_months():
    request=history("那相比上个月呢？")
    assert completed_readonly_summary(request,[bill("2026-01",100)]) is None
    assert completed_readonly_summary(request,[bill("2026-01",100),bill("2026-01",100)]) is None
    done=completed_readonly_summary(request,[bill("2026-01",100),bill("2025-12",50)])
    assert done is not None and "增加" in done
    assert "¥" not in done


def test_financial_operations_and_complex_requests_are_not_shortcut():
    assert completed_readonly_summary(history("查询账单并准备转账 1 元"),[bill("2026-01",100)]) is None
    assert completed_readonly_summary(history("查询账单并计算每一笔差额"),[bill("2026-01",100)]) is None
    assert completed_readonly_summary(history("比较最近三个月账单"),
        [bill("2026-01",100),bill("2025-12",50)]) is None
    assert completed_readonly_summary(history("查询银行卡状态"),[
        ("get_card_status",{"ok":False,"data":None})]) is None
