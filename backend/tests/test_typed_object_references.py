"""Typed financial object references: ownership, card mapping and safe contact binding."""
import asyncio
import json
import re

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.core.security import create_access_token
from app.db.session import get_engine
from app.models import Account, Card, Contact, TransferRequest, User
from app.services.transfer_service import TransferError, execute_transfer
from app.services.vault import VaultError, create_account_token, create_contact_token, resolve
from app.tools.transfer_tools import prepare_transfer_tool


def _entities():
    with Session(get_engine()) as session:
        account = session.exec(select(Account)).one()
        card = session.exec(select(Card)).one()
        contact = session.exec(select(Contact).where(Contact.name == "张三")).one()
        return account.id, card.id, contact.id, account.user_id


def _conversation(client, auth_headers):
    return client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]


def test_verified_card_and_contact_are_server_sourced_not_client_labels(client, auth_headers, monkeypatch):
    account_id, card_id, contact_id, _ = _entities()
    observed = []

    class FakeLLM:
        async def stream(self, messages, tools=None):
            observed.append(messages[-1]["content"])
            yield LLMChunk(content="已识别银行卡和联系人，操作需要额外确认。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    conversation_id = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"
    response = client.post(url, headers=auth_headers, json={
        "content": "看看这张卡，之后转给此联系人",
        "references": [{"kind":"card","id":card_id}, {"kind":"contact","id":contact_id}],
    })
    assert response.status_code == 200
    assert "action_required" not in response.text
    assert len(observed) == 1
    assert re.search(r"account_token=<CARD_[A-Za-z]{32}>", observed[0])
    assert re.search(r"recipient_contact_token=<CONTACT_[A-Za-z]{32}>", observed[0])
    assert "张三" in observed[0]
    history = client.get(url, headers=auth_headers).json()
    assert "银行卡：演示活期账户" in history[0]["content"]
    assert "联系人：张三" in history[0]["content"]
    assert "<CARD_" not in str(history) and "<CONTACT_" not in str(history)
    assert "**** 0001" in history[0]["content"]


def test_reference_ownership_inactive_duplicate_and_conflicting_card_account(client, auth_headers):
    account_id, card_id, contact_id, owner_id = _entities()
    with Session(get_engine()) as session:
        foreign_user = User(username="foreign_ref", password_hash="x", display_name="其他账户")
        session.add(foreign_user)
        session.flush()
        foreign_account = Account(user_id=foreign_user.id, name="他人账户", masked_number="**** 0007",
                                  status="active", currency="CNY", balance_fen=10000)
        foreign_contact = Contact(user_id=foreign_user.id, name="他人联系人",
                                  bank_name="其他银行", masked_phone="139****0099", status="active")
        session.add(foreign_account); session.add(foreign_contact)
        session.flush()
        foreign_card = Card(account_id=foreign_account.id)
        session.add(foreign_card)
        session.commit()
        foreign_account_id, foreign_card_id, foreign_contact_id = foreign_account.id, foreign_card.id, foreign_contact.id

    conversation_id = _conversation(client, auth_headers)
    url = f"/api/chat/conversations/{conversation_id}/messages"
    for kind, other_id in [("account",foreign_account_id), ("card",foreign_card_id), ("contact",foreign_contact_id)]:
        assert client.post(url, headers=auth_headers, json={"content":"查看对象",
            "references":[{"kind":kind,"id":other_id}]}).status_code == 400

    for payload in [
        [{"kind":"card","id":card_id}, {"kind":"card","id":card_id}],
        [{"kind":"contact","id":contact_id}, {"kind":"contact","id":contact_id}],
        [{"kind":"contact","id":0}],
        [{"kind":"holding","id":1}],
        [{"kind":"account","id":account_id},{"kind":"card","id":card_id},
         {"kind":"contact","id":contact_id},{"kind":"contact","id":contact_id}],
    ]:
        assert client.post(url, headers=auth_headers,
            json={"content":"查询","references":payload}).status_code == 422

    # Can't pair one user's valid card with a different active account, even if both are owned.
    with Session(get_engine()) as session:
        another = Account(user_id=owner_id, name="本人另一个账户",
                          masked_number="**** 8888", currency="CNY", balance_fen=20000)
        session.add(another);session.commit();session.refresh(another)
        other_owned_id=another.id
        contact=session.get(Contact,contact_id)
        contact.status="disabled"
        session.add(contact);session.commit()
    assert client.post(url,headers=auth_headers,json={"content":"操作",
        "references":[{"kind":"account","id":other_owned_id},{"kind":"card","id":card_id}]}).status_code == 400
    assert client.post(url,headers=auth_headers,json={"content":"操作",
        "references":[{"kind":"contact","id":contact_id}]}).status_code == 400
    assert client.get(url,headers=auth_headers).json() == []


def test_contact_token_overrides_model_name_and_requires_separate_confirmation(client, auth_headers):
    account_id, card_id, contact_id, user_id = _entities()
    with Session(get_engine()) as session:
        source_token=create_account_token(session,user_id,account_id)
        contact_token=create_contact_token(session,user_id,contact_id)
        session.commit()
    result=asyncio.run(prepare_transfer_tool(
        user_id=user_id, source_token=source_token, recipient_contact_token=contact_token,
        recipient_name="模型伪造的收款人", amount_fen=2000, note="演示"))
    assert result["ok"]
    assert result["action"]["action_type"] == "transfer"
    assert result["action"]["details"]["recipient_name"] == "张三"
    with Session(get_engine()) as session:
        entry=session.get(TransferRequest,result["transfer_id"])
        assert entry.recipient_name=="张三" and entry.status!="completed"
        assert session.get(Account,account_id).balance_fen==500000

    with pytest.raises(TransferError):
        execute_transfer(user_id,result["transfer_id"])

    response=client.post(f"/api/actions/{result['action']['id']}/confirm",headers=auth_headers,
                         json={"token":result["confirmation_token"]})
    assert response.status_code==200
    with Session(get_engine()) as session:
        contact=session.get(Contact,contact_id)
        contact.status="disabled"
        session.add(contact);session.commit()
    with pytest.raises(TransferError):
        execute_transfer(user_id,result["transfer_id"])
    with Session(get_engine()) as session:
        assert session.get(Account,account_id).balance_fen == 500000
        entry=session.get(TransferRequest,result["transfer_id"])
        assert entry.status!="completed"
        with pytest.raises(VaultError):
            resolve(session,user_id,contact_token,"contact","")


def test_contact_token_cannot_be_reused_by_different_user_or_combined_with_phone(client, auth_headers):
    account_id, _, contact_id, user_id = _entities()
    with Session(get_engine()) as session:
        source=create_account_token(session,user_id,account_id)
        contact_token=create_contact_token(session,user_id,contact_id)
        other=User(username="other_token",password_hash="x",display_name="非所有者")
        session.add(other);session.commit();session.refresh(other)
        other_id=other.id
        session.commit()
        with pytest.raises(VaultError):
            resolve(session,other_id,contact_token,"contact","")
    bad=asyncio.run(prepare_transfer_tool(
        user_id=user_id,source_token=source,recipient_contact_token=contact_token,
        target_token="<PHONE_TMP_fake>",recipient_name="张三",amount_fen=1000))
    assert bad["ok"] is False
