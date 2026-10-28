import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import (
    Account, AuditLog, Card, Transaction, User, WealthHolding, WealthOrder, WealthProduct,
)
from app.services.wealth_service import WealthError, execute_order, prepare_subscribe
from app.schemas.wealth import PrepareWealthSubscribeRequest


def _sse_payloads(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def _prepare(client, headers, *, product_id=2, amount_fen=20000, key="wealth_subscribe_0001",
             account_id=1):
    response = client.post("/api/wealth/subscribe/prepare", headers=headers, json={
        "product_id": product_id, "account_id": account_id, "amount_fen": amount_fen,
        "note": "测试申购", "idempotency_key": key,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _prepare_redeem(client, headers, *, product_id=1, amount_fen=20000,
                    key="wealth_redeem_00001", account_id=1):
    response = client.post("/api/wealth/redeem/prepare", headers=headers, json={
        "product_id": product_id, "account_id": account_id, "amount_fen": amount_fen,
        "note": "测试赎回", "idempotency_key": key,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _verify(client, headers, prepared, code=None):
    action, token = prepared["action_id"], prepared["confirmation_token"]
    assert client.post(f"/api/actions/{action}/verification/start", headers=headers,
                       json={"token": token}).status_code == 200
    return client.post(f"/api/actions/{action}/verification/verify", headers=headers,
                       json={"token": token, "code": code or settings.demo_verification_code})


def test_bank_data_routes_are_separate_and_hide_tokens(client, auth_headers):
    products = client.get("/api/bank/wealth/products", headers=auth_headers)
    assert products.status_code == 200
    assert len(products.json()) >= 3
    assert all("product_token" not in item for item in products.json())
    assert client.get("/api/wealth/products", headers=auth_headers).status_code == 404

    holdings = client.get("/api/bank/wealth/holdings", headers=auth_headers)
    assert holdings.status_code == 200
    assert holdings.json()[0]["amount_fen"] == 100_000
    assert all("product_token" not in item for item in holdings.json())
    assert products.headers["cache-control"] == "no-store"

    profile = client.get("/api/bank/wealth/risk-profile", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json()["risk_level"] == "R2"
    assert client.get("/api/bank/wealth/products").status_code == 401


def test_wealth_risk_assessment_is_server_computed(client, auth_headers):
    response = client.post("/api/wealth/risk/assess", headers=auth_headers,
                           json={"answers": [3, 3, 3]})
    assert response.status_code == 200
    assert response.json()["risk_level"] == "R4"
    assert client.get("/api/bank/wealth/risk-profile", headers=auth_headers).json()["score"] == 9
    assert client.post("/api/wealth/risk/assess", headers=auth_headers,
                       json={"answers": [4, 0, 0]}).status_code == 422
    with Session(get_engine()) as session:
        assert len(session.exec(select(AuditLog).where(
            AuditLog.event_type == "wealth_risk_assessed")).all()) == 1


def test_subscribe_requires_red_verification_and_is_idempotent(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    assert prepared["risk_level"] == "red"
    order_path = f"/api/wealth/orders/{prepared['order_id']}/execute"
    assert client.post(order_path, headers=auth_headers).status_code == 400

    assert _verify(client, auth_headers, prepared, "000000").status_code == 400
    assert client.post(order_path, headers=auth_headers).status_code == 400
    assert _verify(client, auth_headers, prepared).status_code == 200
    executed = client.post(order_path, headers=auth_headers)
    assert executed.status_code == 200
    result = executed.json()
    assert result["order_type"] == "subscribe" and result["status"] == "completed"
    assert client.post(order_path, headers=auth_headers).json() == result

    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 480_000
        holding = session.exec(select(WealthHolding).where(
            WealthHolding.product_id == 2)).one()
        assert holding.amount_fen == 20_000
        order = session.get(WealthOrder, prepared["order_id"])
        assert order.status == "completed" and order.transaction_id == result["transaction_id"]
        entry = session.get(Transaction, result["transaction_id"])
        assert entry.category == "理财申购" and entry.direction == "expense"
        assert entry.amount_fen == 20_000
        logs = session.exec(select(AuditLog).where(
            AuditLog.event_type == "wealth_order_completed")).all()
        assert len([log for log in logs if log.result == "success"]) == 1

    retry = _prepare(client, auth_headers)
    assert retry["order_id"] == prepared["order_id"]
    assert retry["confirmation_token"] is None


def test_redeem_requires_verification_and_updates_holding(client, auth_headers):
    prepared = _prepare_redeem(client, auth_headers)
    assert prepared["risk_level"] == "red"
    order_path = f"/api/wealth/orders/{prepared['order_id']}/execute"
    assert client.post(order_path, headers=auth_headers).status_code == 400
    assert _verify(client, auth_headers, prepared).status_code == 200
    result = client.post(order_path, headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["holding_fen"] == 80_000

    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 520_000
        holding = session.exec(select(WealthHolding).where(WealthHolding.product_id == 1)).one()
        assert holding.amount_fen == 80_000
        assert holding.yesterday_earnings_fen == 64
        entry = session.get(Transaction, result.json()["transaction_id"])
        assert entry.category == "理财赎回" and entry.direction == "income"

    too_much = client.post("/api/wealth/redeem/prepare", headers=auth_headers, json={
        "product_id": 1, "account_id": 1, "amount_fen": 90_000, "note": "",
        "idempotency_key": "wealth_redeem_too_much",
    })
    assert too_much.status_code == 400 and "持仓不足" in too_much.json()["detail"]


def test_wealth_validation_frozen_account_lost_card_and_limits(client, auth_headers):
    below_min = client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 1, "account_id": 1, "amount_fen": 5_000, "note": "",
        "idempotency_key": "wealth_below_min_0001",
    })
    assert below_min.status_code == 400
    missing = client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 999, "account_id": 1, "amount_fen": 10_000, "note": "",
        "idempotency_key": "wealth_missing_00001",
    })
    assert missing.status_code == 400
    duplicate = _prepare(client, auth_headers)
    mismatch = client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 2, "account_id": 1, "amount_fen": 30_000, "note": "测试申购",
        "idempotency_key": duplicate["idempotency_key"] if "idempotency_key" in duplicate
        else "wealth_subscribe_0001",
    })
    assert mismatch.status_code == 400

    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        account.status = "frozen"
        session.add(account); session.commit()
    assert client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 2, "account_id": 1, "amount_fen": 10_000, "note": "",
        "idempotency_key": "wealth_frozen_00001",
    }).status_code == 400

    with Session(get_engine()) as session:
        account = session.get(Account, 1)
        account.status = "active"
        card = session.get(Card, 1)
        card.status = "lost"
        session.add(account); session.add(card); session.commit()
    assert client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 2, "account_id": 1, "amount_fen": 10_000, "note": "",
        "idempotency_key": "wealth_lost_card_0001",
    }).status_code == 400


def test_wealth_owner_isolation_and_debug_disabled(client, auth_headers, monkeypatch):
    prepared = _prepare(client, auth_headers)
    with Session(get_engine()) as session:
        other = User(username="wealth_other", password_hash="test", display_name="其他")
        session.add(other); session.commit(); session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    assert client.get("/api/bank/wealth/holdings", headers=other_headers).json() == []
    assert client.post(f"/api/wealth/orders/{prepared['order_id']}/execute",
                       headers=other_headers).status_code == 400

    assert _verify(client, auth_headers, prepared).status_code == 200
    monkeypatch.setattr(settings, "debug", False)
    assert client.post(f"/api/wealth/orders/{prepared['order_id']}/execute",
                       headers=auth_headers).status_code == 400
    assert client.post("/api/wealth/subscribe/prepare", headers=auth_headers, json={
        "product_id": 2, "account_id": 1, "amount_fen": 10_000, "note": "",
        "idempotency_key": "wealth_debug_false_01",
    }).status_code == 400


def test_product_token_is_user_scoped(client, auth_headers):
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
        other = User(username="token_other", password_hash="test", display_name="其他")
        session.add(other); session.commit(); session.refresh(other)
        product_token = session.exec(select(WealthProduct).where(
            WealthProduct.id == 2)).one().id
    payload = PrepareWealthSubscribeRequest.model_validate({
        "product_id": 1, "account_id": None, "amount_fen": 10_000, "note": "",
        "idempotency_key": "wealth_cross_token_01",
    })
    with Session(get_engine()) as session:
        from app.services.vault import create_product_token
        token = create_product_token(session, user_id, product_token)
        session.commit()
    with pytest.raises(WealthError):
        prepare_subscribe(other.id, payload, product_token=token, model_request=True)


def test_agent_can_query_wealth_and_prepare_red_order(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "products", "type": "function", "function": {
                    "name": "get_wealth_products", "arguments": "{}"}}])
            elif self.calls == 2:
                result = json.loads(messages[-1]["content"])
                token = result["data"][0]["product_token"]
                yield LLMChunk(tool_calls=[{"id": "subscribe", "type": "function", "function": {
                    "name": "prepare_wealth_subscribe",
                    "arguments": json.dumps({"product_token": token, "amount_fen": 10_000,
                                             "note": "测试"})}}])
            else:
                yield LLMChunk(content="伪造成交")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "看看理财并买 100 元"})
    events = _sse_payloads(response.text)
    action = next(event for event in events if event["type"] == "action_required")
    assert action["action"]["action_type"] == "wealth_subscribe"
    assert action["action"]["risk_level"] == "red"
    assert action["order_id"]
    assert action["confirmation_token"]
    assert "伪造成交" not in response.text


def test_agent_wealth_holding_rendering_ignores_model_text(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "holdings", "type": "function", "function": {
                    "name": "get_wealth_holdings", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="伪造收益 999999 元")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "我的理财持仓"})
    events = _sse_payloads(response.text)
    assert "模拟理财持仓" in events[-1]["message"]["content"]
    assert "昨日收益" in events[-1]["message"]["content"]
    assert "伪造收益" not in response.text


def test_agent_can_read_risk_profile(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "risk", "type": "function", "function": {
                    "name": "get_wealth_risk_profile", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="伪造风险等级 R4")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "我的理财风险等级"})
    events = _sse_payloads(response.text)
    done = next((event for event in events if event["type"] == "done"), None)
    assert done is not None, response.text
    assert "模拟理财风险等级：R2" in done["message"]["content"]
    assert "伪造风险等级" not in response.text


def test_model_must_use_product_token(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bad", "type": "function", "function": {
                    "name": "prepare_wealth_subscribe",
                    "arguments": json.dumps({"product_id": 2, "amount_fen": 10_000})}}])
            else:
                yield LLMChunk(content="ignored")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages",
                           headers=auth_headers, json={"content": "申购"})
    assert "action_required" not in response.text
    assert "理财申购未准备" in response.text


def test_audit_failure_rolls_back_wealth_order(client, auth_headers, monkeypatch):
    prepared = _prepare(client, auth_headers)
    assert _verify(client, auth_headers, prepared).status_code == 200
    from app.services import wealth_service
    original = wealth_service.record

    def fail_completed(session, **fields):
        if fields["event_type"] == "wealth_order_completed":
            raise RuntimeError("audit unavailable")
        return original(session, **fields)

    monkeypatch.setattr(wealth_service, "record", fail_completed)
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with pytest.raises(RuntimeError):
        execute_order(user_id, prepared["order_id"])
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 500_000
        assert session.exec(select(WealthHolding).where(
            WealthHolding.product_id == 2)).first() is None
        order = session.get(WealthOrder, prepared["order_id"])
        assert order.status == "pending"


def test_wealth_order_concurrent_execute_once(client, auth_headers):
    prepared = _prepare(client, auth_headers)
    assert _verify(client, auth_headers, prepared).status_code == 200
    with Session(get_engine()) as session:
        user_id = session.exec(select(User).where(User.username == "demo")).one().id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_order(user_id, prepared["order_id"]), range(2)))
    assert all(result["status"] == "completed" for result in results)
    with Session(get_engine()) as session:
        assert session.get(Account, 1).balance_fen == 480_000
        entries = session.exec(select(Transaction).where(
            Transaction.category == "理财申购")).all()
        assert len(entries) == 1
        logs = session.exec(select(AuditLog).where(
            AuditLog.event_type == "wealth_order_completed")).all()
        assert len([log for log in logs if log.result == "success"]) == 1
