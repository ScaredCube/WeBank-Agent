from app.services.redaction import mask_text


def test_non_aggressive_mask_keeps_normal_balance_text():
    text = "演示活期账户（**** 0001）\n可用余额：5,000.00 元"
    assert mask_text(text, aggressive=False) == text


def test_non_aggressive_mask_still_hides_long_card_number():
    text = "卡号 4111 1111 1111 1111，余额 5,000.00 元"
    masked = mask_text(text, aggressive=False)
    assert "4111" not in masked
    assert "5,000.00" in masked


def test_aggressive_mask_retains_existing_all_digit_fallback():
    text = "2026-01-01 收入 6,000.00 元"
    assert "*" in mask_text(text, aggressive=True)
