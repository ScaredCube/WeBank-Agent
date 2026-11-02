"""Holdings now use the same authenticated typed-reference channel as accounts."""
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, User, WealthHolding, WealthProduct


def test_holding_reference_is_verified_and_not_a_write_authorization(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as db:
        owner_id = db.exec(select(Account)).one().user_id
        product = WealthProduct(
            name="V2模拟稳健理财", category="稳健理财",
            risk_level="R2", expected_rate_bps=200, min_amount_fen=10000,
        )
        db.add(product); db.flush()
        holding = WealthHolding(user_id=owner_id, product_id=product.id,
                                amount_fen=125000)
        outsider = User(username="outside_v2", display_name="他人", password_hash="x")
        db.add(holding); db.add(outsider); db.flush()
        outsider_holding = WealthHolding(user_id=outsider.id,
                                        product_id=product.id, amount_fen=990000)
        db.add(outsider_holding); db.commit()
        owned_id, foreign_id = holding.id, outsider_holding.id

    observed = []
    class ReadOnlyModel:
        mode = "openai"
        async def stream(self, messages, tools=None):
            observed.append(messages[-1]["content"])
            yield LLMChunk(content="可以继续了解理财持仓的相关信息。")
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: ReadOnlyModel())
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{cid}/messages"
    denied = client.post(url, headers=auth_headers,
                         json={"content": "看看持仓", "references": [{"kind": "holding", "id": foreign_id}]})
    assert denied.status_code == 400
    response = client.post(url, headers=auth_headers,
                           json={"content": "看看这个持仓", "references": [{"kind": "holding", "id": owned_id}]})
    assert response.status_code == 200
    assert len(observed) == 1
    assert f"holding_id={owned_id}" in observed[0]
    assert "V2模拟稳健理财" in observed[0]
    assert "该只读引用不得用于准备交易" in observed[0]
    assert "action_required" not in response.text
    history = client.get(url, headers=auth_headers).json()
    assert "理财持仓：V2模拟稳健理财" in history[0]["content"]
