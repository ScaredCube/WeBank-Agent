"""Subscription cadence must stay within one account; scope is server-authored."""
import asyncio
from datetime import timedelta

from sqlmodel import Session, select

from app.agent.compound_read_summary import summarize_transaction_subscription_review
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import Account, Transaction, User
from app.services.subscription_service import detect_candidates
from app.tools.account_tools import list_recent_transactions
from app.tools.subscription_tools import detect_subscriptions


def _expense(account, reference, days, merchant, value):
    return Transaction(
        account_id=account.id, reference=reference, direction="expense",
        amount_fen=value, balance_after_fen=account.balance_fen,
        counterparty=merchant, category="消费", note="",
        occurred_at=utcnow() - timedelta(days=days),
    )


def test_two_accounts_cannot_be_combined_into_false_periodic_candidate(
    client, auth_headers,
):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        first = session.exec(select(Account).where(Account.user_id == user.id)).first()
        second = Account(
            user_id=user.id, name="备用模拟账户", masked_number="**** 7777",
            balance_fen=500000, currency="CNY",
        )
        session.add(second)
        session.commit()
        session.refresh(second)

        # Same merchant and amount in different months, but only one occurrence
        # in each account. This used to become one false positive.
        session.add(_expense(first, "cross-acct-one", 65, "跨账户周期测试", 1357))
        session.add(_expense(second, "cross-acct-two", 5, "跨账户周期测试", 1357))
        session.commit()
        assert not any(
            item["merchant"] == "跨账户周期测试"
            for item in detect_candidates(session, user.id)
        )
        # A true two-month sequence in one account remains detectable; the
        # payment in the other account must NOT inflate occurrences to three.
        session.add(_expense(first, "cross-acct-three", 5, "跨账户周期测试", 1357))
        session.commit()
        detected = [
            item for item in detect_candidates(session, user.id)
            if item["merchant"] == "跨账户周期测试"
        ]
        assert len(detected) == 1
        assert detected[0]["occurrences"] == 2


def test_tool_scopes_are_authored_by_server_without_account_identifiers(
    client, auth_headers,
):
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        transactions = asyncio.run(list_recent_transactions(
            session, user.id, limit=5,
        ))
        detected = asyncio.run(detect_subscriptions(session, user.id))
    assert transactions["ok"] and detected["ok"]
    assert transactions["scope"] == {"kind": "single_account", "max_rows": 5}
    assert detected["scope"] == {"kind": "all_user_accounts", "lookback_days": 186}
    assert "account_id" not in str(transactions["scope"])
    assert "account_token" not in str(transactions["scope"])
    assert "account_id" not in str(detected["scope"])
    assert "account_token" not in str(detected["scope"])


def test_compound_reply_exposes_distinct_scopes_only_when_verified():
    transaction = ("list_recent_transactions", {
        "ok": True, "data": [], "scope": {"kind": "single_account", "max_rows": 5},
    })
    detection = ("detect_subscriptions", {
        "ok": True, "data": [],
        "scope": {"kind": "all_user_accounts", "lookback_days": 186},
    })
    question = "查最近交易记录并识别疑似订阅"
    text = summarize_transaction_subscription_review(
        [transaction, detection], user_request=question,
    )
    assert "单个模拟账户" in text and "本人所有模拟账户近186天" in text
    assert "不能直接逐笔对应" in text

    without_provenance = summarize_transaction_subscription_review(
        [transaction, ("detect_subscriptions", {"ok": True, "data": []})],
        user_request=question,
    )
    assert "无法核验两个查询的账户与时间范围" in without_provenance
    assert "本人所有模拟账户近186天" not in without_provenance

    tampered_scope = summarize_transaction_subscription_review(
        [transaction, ("detect_subscriptions", {
            "ok": True, "data": [],
            "scope": {"kind": "all_user_accounts", "lookback_days": 7},
        })],
        user_request=question,
    )
    assert "无法核验两个查询的账户与时间范围" in tampered_scope
