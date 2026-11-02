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


def test_category_summary_requires_trusted_aggregates_and_no_extra_goal():
    result = bill("2026-01", 1000)
    result[1]["data"]["categories"] = [{"category": "餐饮", "amount_fen": 1000, "count": 2}]
    request = "查询2026-01消费账单并展示分类汇总"
    assert completed_readonly_summary(history(request), [result]) == "账单已查询，消费分类汇总见下方结果卡。"
    for extra in ("并查余额", "并准备转账", "分析占比", "哪个类别最多", "查看逐笔明细", "解释原因", "检查订阅", "只看餐饮", "筛选分类", "查看商户"):
        assert completed_readonly_summary(history(request + extra), [result]) is None
    assert completed_readonly_summary(history(request), [bill("2026-01", 1000)]) is None


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


def test_compound_tasks_do_not_close_after_one_verified_bill():
    compound = (
        "查看本月账单，并识别重复订阅",
        "查询本月账单和最近的交易流水",
        "查账单后解释为什么消费增加",
        "查询消费并查看账户余额",
        "查账单，然后帮我排查异常扣款",
        "分析本月消费和理财持仓",
        "查账单并核对订阅",
    )
    for request in compound:
        assert completed_readonly_summary(
            history(request), [bill("2026-01", 100)],
            user_request=request,
        ) is None


def test_only_original_user_request_can_authorize_fast_completion():
    decorated = "请查询本月账单" + chr(10) * 2 + "[普通备注]" + chr(10) + "另外检查订阅"
    model_message = history(
        "请查询本月账单" + chr(10) * 2 + "[以下是服务端验证的金融对象：已核验账户]"
    )
    # Legacy callers fail closed, rather than truncate at an untrusted delimiter.
    assert completed_readonly_summary(model_message, [bill("2026-01", 100)]) is None
    # Server-provided original request is authoritative for completion checks.
    assert completed_readonly_summary(
        model_message, [bill("2026-01", 100)],
        user_request="请查询本月账单",
    ) == "账单已查询，明细见下方结果卡。"
    assert completed_readonly_summary(
        history(decorated), [bill("2026-01", 100)],
        user_request=decorated,
    ) is None


def test_explicit_multi_month_request_does_not_finish_after_one_snapshot():
    requests = (
        "查询2026年1月和2月的账单",
        "请分别查2026-01、2026-02账单",
        "把1月和2月消费列出来",
    )
    for request in requests:
        assert completed_readonly_summary(
            history(request), [bill("2026-01", 100)],
            user_request=request,
        ) is None


def test_card_reference_alone_does_not_require_card_status_tool():
    # Asking for a card's bill is not the same as asking for card status.
    assert completed_readonly_summary(
        history("查询这张银行卡的月度账单"), [bill("2026-01", 100)],
    ) == "账单已查询，明细见下方结果卡。"


def test_financial_operations_and_complex_requests_are_not_shortcut():
    assert completed_readonly_summary(history("查询账单并准备转账 1 元"),[bill("2026-01",100)]) is None
    assert completed_readonly_summary(history("查询账单并计算每一笔差额"),[bill("2026-01",100)]) is None
    assert completed_readonly_summary(history("比较最近三个月账单"),
        [bill("2026-01",100),bill("2025-12",50)]) is None
    assert completed_readonly_summary(history("查询银行卡状态"),[
        ("get_card_status",{"ok":False,"data":None})]) is None
