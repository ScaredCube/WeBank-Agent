"""Cross-business regressions: money classification and operation identity."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, delete, select

from app.core.config import settings
from app.core.time import utcnow
from app.db.session import get_engine
from app.models import (Account, AuditLog, Card, CardLossRequest, DataToken, PendingAction,
                        OperationPreparation, Subscription, SubscriptionCancelRequest,
                        Transaction, TransferRequest, User, WealthOrder)
from app.core.security import create_access_token
from app.services.audit_service import request_context
from app.services.vault import create_account_token, create_subscription_token, revoke
from app.tools.transfer_tools import prepare_transfer_tool
from tests.test_wealth import _prepare, _prepare_redeem, _verify


def test_wealth_cashflows_are_not_consumption(client, auth_headers):
    with Session(get_engine()) as session:
        session.exec(delete(Transaction))
        session.commit()
    buy = _prepare(client, auth_headers)
    sell = _prepare_redeem(client, auth_headers, amount_fen=10000)
    for order in (buy, sell):
        assert _verify(client, auth_headers, order).status_code == 200
        assert client.post(f"/api/wealth/orders/{order['order_id']}/execute",
                           headers=auth_headers).status_code == 200
    # Keep month independent of wall clock and add repeated investments: these
    # must not trigger the duplicate *consumption* rule either.
    with Session(get_engine()) as session:
        for entry in session.exec(select(Transaction)).all():
            entry.occurred_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
            session.add(entry)
        session.add(Transaction(account_id=1, reference="second-investment", direction="expense",
                                amount_fen=20000, balance_after_fen=470000,
                                counterparty="稳健模拟理财", category="理财申购",
                                occurred_at=datetime(2026, 10, 15, tzinfo=timezone.utc)))
        session.commit()
    result = client.get("/api/bills/monthly?month=2026-10&account_id=1", headers=auth_headers)
    assert result.status_code == 200, result.text
    bill = result.json()
    assert bill["consumption_fen"] == 0
    assert bill["consumption_count"] == 0 and bill["categories"] == []
    assert bill["expense_fen"] == 40000 and bill["income_fen"] == 10000
    assert bill["investment_out_fen"] == 40000 and bill["investment_out_count"] == 2
    assert bill["investment_in_fen"] == 10000 and bill["investment_in_count"] == 1
    assert bill["anomalies"] == []
    from app.tools.presentation import render_tool_result
    rendered = render_tool_result("get_monthly_bill", {"ok": True, "data": bill})
    assert "400.00" in rendered and "理财" in rendered


KINDS = ("card", "subscription")


def prepare_path(kind, entity=1):
    return (f"/api/cards/{entity}/loss/prepare" if kind == "card"
            else f"/api/subscriptions/{entity}/cancel/prepare")


def execute_path(kind, action):
    return (f"/api/cards/loss/{action}/execute" if kind == "card"
            else f"/api/subscriptions/cancel/{action}/execute")


def authorize(client, headers, kind, prepared):
    if kind == "card":
        assert _verify(client, headers, prepared).status_code == 200
    else:
        assert client.post(f"/api/actions/{prepared['action_id']}/confirm", headers=headers,
                           json={"token": prepared["confirmation_token"]}).status_code == 200


@pytest.mark.parametrize("kind", KINDS)
def test_prepare_retries_reuse_action_without_reissuing_secret(client, auth_headers, kind):
    payload = {"idempotency_key": "operation-retry-0001"}
    first = client.post(prepare_path(kind), headers=auth_headers, json=payload).json()
    repeated = client.post(prepare_path(kind), headers=auth_headers, json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["action_id"] == first["action_id"]
    assert repeated.json()["confirmation_token"] is None
    authorize(client, auth_headers, kind, first)
    path = execute_path(kind, first["action_id"])
    assert client.post(path, headers=auth_headers).status_code == 200
    assert client.post(path, headers=auth_headers).status_code == 200
    final = client.post(prepare_path(kind), headers=auth_headers, json=payload)
    assert final.status_code == 200 and final.json()["action_id"] == first["action_id"]
    assert final.json()["confirmation_token"] is None
    with Session(get_engine()) as session:
        model = CardLossRequest if kind == "card" else SubscriptionCancelRequest
        assert len(session.exec(select(model)).all()) == 1
        assert session.get(PendingAction, first["action_id"]).status == "completed"


@pytest.mark.parametrize("kind", KINDS)
def test_same_key_with_different_entity_is_rejected(client, auth_headers, kind):
    if kind == "card":
        with Session(get_engine()) as session:
            account = Account(user_id=1, name="second", masked_number="****0002", balance_fen=10000)
            session.add(account); session.flush()
            session.add(Card(account_id=account.id)); session.commit()
    payload = {"idempotency_key": "operation-conflict-01"}
    assert client.post(prepare_path(kind), headers=auth_headers, json=payload).status_code == 200
    assert client.post(prepare_path(kind, 2), headers=auth_headers, json=payload).status_code == 400


@pytest.mark.parametrize("kind", KINDS)
def test_concurrent_prepare_with_same_key_creates_one_action(client, auth_headers, kind):
    def prepare(_):
        return client.post(prepare_path(kind), headers=auth_headers,
                           json={"idempotency_key": "concurrent-prepare-01"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(prepare, range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["action_id"] for r in responses}) == 1
    assert sum(r.json()["confirmation_token"] is not None for r in responses) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_revocation_after_prepare_blocks_execution(client, auth_headers, kind):
    with Session(get_engine()) as session:
        token = (create_account_token(session, 1, 1) if kind == "card"
                 else create_subscription_token(session, 1, 1))
        session.commit()
    prepared = client.post(prepare_path(kind), headers=auth_headers).json()
    authorize(client, auth_headers, kind, prepared)
    with Session(get_engine()) as session:
        revoke(session, 1, token); session.commit()
    assert client.post(execute_path(kind, prepared["action_id"]), headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Card if kind == "card" else Subscription, 1).status == "active"


def test_wealth_verification_cannot_authorize_another_action_type(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    assert _verify(client, auth_headers, prepared).status_code == 200
    with Session(get_engine()) as session:
        action = session.get(PendingAction, prepared["action_id"])
        action.action_type = "card_loss"
        session.add(action); session.commit()
    assert client.post(f"/api/wealth/orders/{prepared['order_id']}/execute",
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000


def test_transfer_completion_also_completes_action(client, auth_headers, monkeypatch):
    hour = utcnow().astimezone(timezone(timedelta(hours=8))).hour
    monkeypatch.setattr(settings, "risk_night_start_hour", (hour + 1) % 24)
    monkeypatch.setattr(settings, "risk_night_end_hour", (hour + 2) % 24)
    prepared = client.post("/api/transfers/prepare", headers=auth_headers, json={
        "account_id": 1, "recipient_name": "demo", "amount_fen": 100,
        "idempotency_key": "complete-action-0001"}).json()
    authorize(client, auth_headers, "subscription", prepared)
    assert client.post(f"/api/transfers/{prepared['transfer_id']}/execute",
                       headers=auth_headers).status_code == 200
    with Session(get_engine()) as session:
        assert session.get(PendingAction, prepared["action_id"]).status == "completed"


def test_agent_repeat_preparation_in_same_request_does_not_duplicate(client, auth_headers):
    async def run():
        context = request_context.set("server-request-fixed-for-test")
        try:
            first = await prepare_transfer_tool(user_id=1, recipient_name="demo", amount_fen=100)
            assert first["ok"]
            await prepare_transfer_tool(user_id=1, recipient_name="demo", amount_fen=100)
            # Changed parameters in the same operation must not create a new order.
            changed = await prepare_transfer_tool(user_id=1, recipient_name="demo", amount_fen=200)
            assert not changed["ok"]
        finally:
            request_context.reset(context)
    asyncio.run(run())
    with Session(get_engine()) as session:
        assert len(session.exec(select(TransferRequest)).all()) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_preparation_key_is_scoped_to_user(client, auth_headers, kind):
    with Session(get_engine()) as session:
        user = User(username="other-preparer", password_hash="unused")
        session.add(user); session.flush()
        other_id = user.id
        if kind == "card":
            account = Account(user_id=other_id, name="other", masked_number="****0002", balance_fen=10000)
            session.add(account); session.flush()
            entity = Card(account_id=account.id)
        else:
            entity = Subscription(user_id=other_id, merchant="other", amount_fen=100,
                                  next_charge_date=utcnow().date())
        session.add(entity); session.commit(); session.refresh(entity)
        entity_id = entity.id
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    body = {"idempotency_key": "same-key-two-users-01"}
    first = client.post(prepare_path(kind), headers=auth_headers, json=body).json()
    assert client.post(prepare_path(kind), headers=other_headers, json=body).status_code == 400
    other = client.post(prepare_path(kind, entity_id), headers=other_headers, json=body)
    assert other.status_code == 200
    assert other.json()["action_id"] != first["action_id"]


@pytest.mark.parametrize("kind", KINDS)
def test_expired_preparation_retry_does_not_renew_authorization(client, auth_headers, kind):
    body = {"idempotency_key": "expired-prepare-0001"}
    first = client.post(prepare_path(kind), headers=auth_headers, json=body).json()
    with Session(get_engine()) as session:
        action = session.get(PendingAction, first["action_id"])
        action.expires_at = utcnow() - timedelta(seconds=1)
        session.add(action); session.commit()
    retry = client.post(prepare_path(kind), headers=auth_headers, json=body).json()
    assert retry["action_id"] == first["action_id"] and retry["confirmation_token"] is None
    assert client.post(execute_path(kind, first["action_id"]), headers=auth_headers).status_code == 400


@pytest.mark.parametrize("kind", KINDS)
def test_prepare_audit_failure_rolls_back_receipt_and_action(client, auth_headers, monkeypatch, kind):
    from app.services import card_service, subscription_service
    service = card_service if kind == "card" else subscription_service
    original = service.record
    event = "card_loss_prepared" if kind == "card" else "subscription_cancel_prepared"
    def fail(session, **fields):
        if fields["event_type"] == event:
            raise RuntimeError("synthetic audit outage")
        return original(session, **fields)
    monkeypatch.setattr(service, "record", fail)
    body = {"idempotency_key": "prepare-rollback-0001"}
    with pytest.raises(RuntimeError, match="synthetic audit outage"):
        client.post(prepare_path(kind), headers=auth_headers, json=body)
    with Session(get_engine()) as session:
        assert session.exec(select(OperationPreparation)).all() == []
        assert session.exec(select(PendingAction)).all() == []
        assert session.exec(select(CardLossRequest if kind == "card" else SubscriptionCancelRequest)).all() == []
        assert any(log.result == "failed" for log in session.exec(select(AuditLog)).all())
    monkeypatch.setattr(service, "record", original)
    assert client.post(prepare_path(kind), headers=auth_headers, json=body).status_code == 200


@pytest.mark.parametrize("kind", KINDS)
def test_missing_legacy_binding_cannot_execute(client, auth_headers, kind):
    first = client.post(prepare_path(kind), headers=auth_headers).json()
    authorize(client, auth_headers, kind, first)
    with Session(get_engine()) as session:
        session.exec(delete(OperationPreparation)); session.commit()
    assert client.post(execute_path(kind, first["action_id"]), headers=auth_headers).status_code == 400


@pytest.mark.parametrize("kind", KINDS)
def test_invalid_key_is_rejected_without_action(client, auth_headers, kind):
    for key in ("short", "x" * 65, "invalid key with spaces", 1234567890123456):
        assert client.post(prepare_path(kind), headers=auth_headers,
                           json={"idempotency_key": key}).status_code == 422
    with Session(get_engine()) as session:
        assert session.exec(select(PendingAction)).all() == []


@pytest.mark.parametrize("kind", ("account", "product"))
def test_wealth_rechecks_revoked_reference_before_debit(client, auth_headers, kind):
    first = _prepare(client, auth_headers)
    assert _verify(client, auth_headers, first).status_code == 200
    with Session(get_engine()) as session:
        order = session.get(WealthOrder, first["order_id"])
        row = session.get(DataToken, order.account_token_id if kind == "account" else order.product_token_id)
        revoke(session, 1, row.token); session.commit()
    assert client.post(f"/api/wealth/orders/{first['order_id']}/execute",
                       headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500000


@pytest.mark.parametrize("kind", ("card", "subscription", "wealth"))
def test_agent_preparation_reuses_identity_for_each_business(client, auth_headers, kind):
    from app.tools.card_tools import prepare_card_loss
    from app.tools.subscription_tools import prepare_cancel_subscription
    from app.tools.wealth_tools import prepare_wealth_subscribe
    from app.services.vault import create_product_token
    with Session(get_engine()) as session:
        if kind == "card":
            fn, args = prepare_card_loss, {}
        elif kind == "subscription":
            fn, args = prepare_cancel_subscription, {"subscription_token": create_subscription_token(session, 1, 1)}
        else:
            fn, args = prepare_wealth_subscribe, {"product_token": create_product_token(session, 1, 2), "amount_fen": 20000}
        session.commit()
    async def run():
        context = request_context.set("server-same-logical-operation")
        try:
            assert (await fn(user_id=1, **args))["ok"]
            second = await fn(user_id=1, **args)
            assert not second["ok"]  # no secret replayed to model or client
        finally:
            request_context.reset(context)
    asyncio.run(run())
    with Session(get_engine()) as session:
        assert len(session.exec(select(PendingAction)).all()) == 1
