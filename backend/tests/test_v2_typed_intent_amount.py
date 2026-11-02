"""The verified drag intent accepts the UI's numeric CNY field end-to-end."""
import json

from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import Account, WealthProduct, WealthHolding


def test_holdings_conversion_amount_reaches_agent_without_missing_amount_fallback(
    client, auth_headers, monkeypatch,
):
    with Session(get_engine()) as db:
        owner_id = db.exec(select(Account)).one().user_id
        ids = []
        for index in range(2):
            product = WealthProduct(
                name=f"V2转换产品_{index}", category="稳健理财",
                risk_level="R2", expected_rate_bps=220, min_amount_fen=100,
            )
            db.add(product)
            db.flush()
            holding = WealthHolding(
                user_id=owner_id, product_id=product.id, amount_fen=300000,
            )
            db.add(holding); db.flush()
            ids.append(holding.id)
        db.commit()

    seen = []
    class Model:
        mode = "openai"
        async def stream(self, messages, tools=None):
            seen.append((messages, tools))
            if tools is None:
                yield LLMChunk(content=json.dumps({
                    "question": "请问还需要补充其他转换信息吗？"
                }, ensure_ascii=False))
            else:
                yield LLMChunk(content="请问还需要补充其他转换信息吗？")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: Model())
    cid = client.post("/api/chat/conversations", headers=auth_headers, json={}).json()["id"]
    response = client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={
            "content": "转换金额：1000",
            "intent": {
                "action": "convert",
                "source": {"kind": "holding", "id": ids[0]},
                "target": {"kind": "holding", "id": ids[1]},
            },
        },
    )
    assert response.status_code == 200
    assert seen and seen[0][1] is not None
    assert any("转换金额：1000" in str(msg.get("content")) for msg in seen[0][0])
    assert "请在消息中提供一个明确金额" not in response.text
