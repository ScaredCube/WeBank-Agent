import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.agent.registry import RiskLevel
from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import Account, Transaction, User
from app.services.vault import create_account_token
from app.tools.register import create_readonly_registry


def add_entry(session, account_id, reference, when, amount=100, direction="expense", category="餐饮", counterparty="餐厅"):
    session.add(Transaction(account_id=account_id, reference=reference, occurred_at=when, direction=direction,
        amount_fen=amount, balance_after_fen=500000, category=category, counterparty=counterparty))


def test_month_boundary_full_data_and_transfer_classification(client, auth_headers):
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).one()
        # Beijing February begins at 16:00 UTC January 31, and ends at 16:00 UTC February 28.
        start = datetime(2026, 1, 31, 16, tzinfo=timezone.utc)
        add_entry(session, account.id, "before", start - timedelta(seconds=1), 9999)
        for i in range(55):
            add_entry(session, account.id, f"bill-{i}", start + timedelta(minutes=20 * i), 100)
        add_entry(session, account.id, "duplicate", start + timedelta(minutes=1), 100)
        add_entry(session, account.id, "salary", start, 30000, "income", "工资", "公司")
        add_entry(session, account.id, "transfer", start, 9000, "expense", "模拟转账", "某人")
        add_entry(session, account.id, "transfer-in", start, 2000, "income", "模拟转账", "某人")
        add_entry(session, account.id, "end", datetime(2026, 2, 28, 16, tzinfo=timezone.utc), 9999)
        session.commit()
    response = client.get("/api/bills/monthly", params={"month": "2026-02"}, headers=auth_headers)
    assert response.status_code == 200
    bill = response.json()
    assert bill["income_fen"] == 32000 and bill["expense_fen"] == 14600
    assert bill["consumption_fen"] == 5600 and bill["consumption_count"] == 56
    assert bill["categories"] == [{"category": "餐饮", "amount_fen": 5600, "count": 56}]
    assert bill["transfer_out_fen"] == 9000 and bill["transfer_in_fen"] == 2000
    assert len(bill["anomalies"]) == 1 and bill["anomalies"][0]["status"] == "需核对"
    assert response.headers["cache-control"] == "no-store"
    audit = client.get("/api/audit", headers=auth_headers).json()
    assert any(e["tool"] == "get_monthly_bill" and e["event_type"] == "tool_result" and e["result"] == "success" for e in audit)


def test_empty_invalid_month_and_account_isolation(client, auth_headers):
    empty = client.get("/api/bills/monthly", params={"month": "2025-12"}, headers=auth_headers)
    assert empty.status_code == 200 and empty.json()["expense_fen"] == 0 and empty.json()["categories"] == []
    for month in ("2026-13", "2026-2", "bad", "0000-01"):
        assert client.get("/api/bills/monthly", params={"month": month}, headers=auth_headers).status_code == 400
    with Session(get_engine()) as session:
        owner = session.exec(select(User).where(User.username == "demo")).one()
        account = session.exec(select(Account).where(Account.user_id == owner.id)).one()
        token = create_account_token(session, owner.id, account.id)
        other = User(username="bill_other", password_hash="test", display_name="其他用户")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
        account_id, other_id = account.id, other.id
    assert client.get("/api/bills/monthly", params={"month": "2026-01", "account_id": account_id}, headers=other_headers).status_code == 400
    handler = create_readonly_registry().get("get_monthly_bill")
    assert handler.risk == RiskLevel.GREEN
    with Session(get_engine()) as session:
        result = asyncio.run(handler.handler(session, other_id, month="2026-01", account_token=token))
        assert not result["ok"]
        account = session.get(Account, account_id)
        account.status = "frozen"
        session.add(account)
        session.commit()
    assert client.get("/api/bills/monthly", params={"month": "2026-01", "account_id": account_id}, headers=auth_headers).status_code == 400


def test_chat_bill_tool_fixed_rendering_and_audit(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bill", "type": "function", "function": {
                    "name": "get_monthly_bill", "arguments": json.dumps({"month": "2026-01"})}}])
            else:
                assert json.loads(messages[-1]["content"])["data"]["expense_fen"] == 100000
                yield LLMChunk(content="虚构金额999999元")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=auth_headers,
                           json={"content": "分析2026年1月的消费"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    content = events[-1]["message"]["content"]
    assert "账单已查询" in content and "999999" not in content
    assert events[0]["type"] == "bill_result"
    assert events[0]["data"]["expense_fen"] == 100000
    audit = client.get("/api/audit", headers=auth_headers).json()
    assert any(e["tool"] == "get_monthly_bill" and e["conversation_id"] == conversation_id
               and e["event_type"] == "tool_result" for e in audit)


@pytest.mark.parametrize("now,expected_month,expected_amount", [
    (datetime(2026, 12, 31, 15, 59, 59, tzinfo=timezone.utc), "2026-12", 110),
    (datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc), "2027-01", 220),
])
def test_default_month_uses_beijing_year_boundary(client, auth_headers, monkeypatch, now, expected_month, expected_amount):
    monkeypatch.setattr("app.services.bill_service.utcnow", lambda: now)
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).one()
        boundary = datetime(2026, 12, 31, 16, tzinfo=timezone.utc)
        add_entry(session, account.id, "last-second-of-december", boundary - timedelta(seconds=1), 110)
        add_entry(session, account.id, "first-second-of-january", boundary, 220)
        session.commit()
    response = client.get("/api/bills/monthly", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["month"] == expected_month
    assert response.json()["expense_fen"] == expected_amount
    handler = create_readonly_registry().get("get_monthly_bill")
    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.username == "demo")).one()
        result = asyncio.run(handler.handler(session, user.id))
    assert result["ok"] and result["data"]["month"] == expected_month
    assert result["data"]["expense_fen"] == expected_amount


def test_bill_masks_sensitive_fields_in_api_model_and_chat(client, auth_headers, monkeypatch):
    phone = "13812345678"
    card = "4111111111111111"  # Synthetic test number, not an account.
    private_note = "PRIVATE_NOTE_NOT_FOR_OUTPUT"
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).one()
        account.name = f"账户 {phone}"
        account.masked_number = f"卡号 {card}"
        session.add(account)
        when = datetime(2026, 2, 1, tzinfo=timezone.utc)
        for i in range(2):
            add_entry(session, account.id, f"privacy-{i}", when + timedelta(minutes=i),
                      1200, category=f"分类 {card}", counterparty=f"商户 {phone}")
            row = session.exec(select(Transaction).where(Transaction.reference == f"privacy-{i}")).one()
            row.note = private_note
            session.add(row)
        session.commit()

    def assert_private(text):
        assert phone not in text and card not in text and private_note not in text
        assert "[敏感号码已隐藏]" in text

    response = client.get("/api/bills/monthly", params={"month": "2026-02"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["expense_fen"] == 2400 and len(data["anomalies"]) == 1
    assert_private(json.dumps(data, ensure_ascii=False))
    for value in (data["account_name"], data["masked_number"], data["categories"][0]["category"],
                  data["anomalies"][0]["counterparty"]):
        assert "[敏感号码已隐藏]" in value

    class FakeLLM:
        calls = 0
        tool_result = None

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bill-privacy", "type": "function", "function": {
                    "name": "get_monthly_bill", "arguments": json.dumps({"month": "2026-02"})}}])
            else:
                self.tool_result = messages[-1]["content"]
                yield LLMChunk(content="不会采用模型生成的账单文本")

    llm = FakeLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    chat = client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=auth_headers,
                       json={"content": "分析2026年2月的消费"})
    assert chat.status_code == 200
    events = [json.loads(line[6:]) for line in chat.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "done"
    assert llm.tool_result is not None
    assert_private(llm.tool_result)
    assert events[-1]["message"]["content"] == "账单已查询，明细见下方结果卡。"
    assert_private(json.dumps(events[0]["data"], ensure_ascii=False))
    assert len(events[0]["data"]["anomalies"]) == 1
    assert_private(chat.text)

def test_chat_typed_account_reference_is_verified_and_bill_result_is_trusted(client, auth_headers, monkeypatch):
    """The selected account is resolved server-side, not from client-provided names or tokens."""
    import re

    with Session(get_engine()) as session:
        account = session.exec(select(Account)).one()
        account_id = account.id

    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                context = messages[-1]["content"]
                match = re.search(r"<CARD_[A-Za-z]{32}>", context)
                assert match is not None
                assert "客户端" not in context
                yield LLMChunk(tool_calls=[{"id": "bill-typed", "type": "function",
                    "function": {"name": "get_monthly_bill",
                                 "arguments": json.dumps({"month": "2026-01", "account_token": match.group()})}}])
            else:
                result = json.loads(messages[-1]["content"])
                assert result["ok"]
                assert result["data"]["expense_fen"] == 100000
                yield LLMChunk(content="这段模型文字不能自行决定账单金额。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"
    response = client.post(url, headers=auth_headers, json={"content": "分析这张账户的月度消费",
        "references": [{"kind": "account", "id": account_id}]})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["type"] for event in events] == ["bill_result", "delta", "done"]
    assert events[0]["data"]["expense_fen"] == 100000
    assert "account_token" not in json.dumps(events[0], ensure_ascii=False)
    assert "<CARD_" not in response.text
    history = client.get(url, headers=auth_headers).json()
    assert len(history) == 2
    assert "[已引用对象：账户：" in history[0]["content"]
    assert "<CARD_" not in str(history)


def test_chat_rejects_unowned_or_invalid_account_references_before_writing_message(client, auth_headers):
    with Session(get_engine()) as session:
        other = User(username="reference_other", password_hash="test", display_name="其他用户")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_account = Account(user_id=other.id, name="其他人的账户", masked_number="****0000",
                                currency="CNY", balance_fen=100, status="active")
        session.add(other_account)
        session.commit()
        session.refresh(other_account)
        foreign_id = other_account.id

    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"
    assert client.post(url, headers=auth_headers, json={"content": "查消费",
        "references": [{"kind": "account", "id": foreign_id}]}).status_code == 400
    assert client.post(url, headers=auth_headers, json={"content": "查消费",
        "references": [{"kind": "untrusted", "id": 1}]}).status_code == 422
    assert client.post(url, headers=auth_headers, json={"content": "查消费",
        "references": [{"kind": "account", "id": -1}]}).status_code == 422
    assert client.post(url, headers=auth_headers, json={"content": "查消费",
        "references": [{"kind": "account", "id": 1}, {"kind": "account", "id": 2}]}).status_code == 422
    assert client.get(url, headers=auth_headers).json() == []

def test_bill_result_is_encrypted_and_restores_with_its_original_assistant_message(client, auth_headers, monkeypatch):
    from app.models import MessageResult
    from app.services.vault import decrypt_result_snapshot

    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bill-history", "type": "function", "function": {
                    "name": "get_monthly_bill", "arguments": json.dumps({"month": "2026-01"})}}])
            else:
                yield LLMChunk(content="不采用模型自报金额。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"
    response = client.post(url, json={"content": "查一月账单"}, headers=auth_headers)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    saved = events[-1]["message"]
    assert saved["bill_result"]["month"] == "2026-01"
    assert saved["bill_result"]["expense_fen"] == 100000

    with Session(get_engine()) as session:
        snapshots = session.exec(select(MessageResult)).all()
        assert len(snapshots) == 1
        row = snapshots[0]
        assert row.message_id == saved["id"]
        assert row.kind == "monthly_bill"
        assert "2026-01" not in row.ciphertext
        assert "100000" not in row.ciphertext
        assert decrypt_result_snapshot(row.ciphertext, row.key_version)["expense_fen"] == 100000

    history = client.get(url, headers=auth_headers)
    assert history.headers["cache-control"] == "no-store"
    assert history.json()[-1]["bill_result"] == saved["bill_result"]
    assert history.json()[0]["bill_result"] is None

    other = User(username="snapshot_other", password_hash="test", display_name="其他用户")
    with Session(get_engine()) as session:
        session.add(other)
        session.commit()
        session.refresh(other)
        other_id = other.id
    different_user = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    assert client.get(url, headers=different_user).status_code == 404


def test_invalid_snapshot_key_keeps_history_readable_without_leaking_data(client, auth_headers, monkeypatch):
    from app.models import MessageResult
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "bill-retired-key", "type": "function", "function": {
                    "name": "get_monthly_bill", "arguments": json.dumps({"month": "2026-01"})}}])
            else:
                yield LLMChunk(content="工具查询已完成")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"
    client.post(url, headers=auth_headers, json={"content": "查月账单"})
    with Session(get_engine()) as session:
        snapshot = session.exec(select(MessageResult)).one()
        snapshot.ciphertext = "tampered-invalid-ciphertext"
        session.add(snapshot)
        session.commit()
    history = client.get(url, headers=auth_headers)
    assert history.status_code == 200
    assert history.json()[-1]["content"]
    assert history.json()[-1]["bill_result"] is None
