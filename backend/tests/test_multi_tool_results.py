"""One Agent reply can preserve more than one trusted tool result in order."""
import json

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.agent.llm import LLMChunk
from app.db.session import get_engine
from app.models import MessageResult
from app.schemas.tool_results import ToolResultBundle
from app.services.vault import decrypt_result_snapshot


def test_multiple_tool_results_survive_encrypted_history(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[
                    {"id": "monthly", "type": "function",
                     "function": {"name": "get_monthly_bill", "arguments": json.dumps({"month": "2026-01"})}},
                    {"id": "card", "type": "function",
                     "function": {"name": "get_card_status", "arguments": "{}"}},
                ])
            else:
                yield LLMChunk(content="两项银行数据已经核验。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    cid = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{cid}/messages"
    resp = client.post(url, headers=auth_headers, json={"content": "查这月账单和银行卡状态"})
    assert resp.status_code == 200
    events = [json.loads(row[6:]) for row in resp.text.splitlines() if row.startswith("data: ")]
    assert [x["type"] for x in events if x["type"] != "ui_status"] == ["bill_result", "card_result", "delta", "done"]
    message = events[-1]["message"]
    assert message["content"] == "银行卡状态和账单已查询，明细见下方结果卡。"
    result = message["tool_results"]
    assert [x["kind"] for x in result] == ["monthly_bill", "card_status"]
    assert result[0]["data"]["month"] == "2026-01"
    assert result[0]["data"]["expense_fen"] == 100000
    assert result[1]["data"]["cards"][0]["card_id"] == 1
    assert "account_token" not in str(result) and "<CARD_" not in str(result)
    assert message["bill_result"] == result[0]["data"]
    assert message["card_result"] == result[1]["data"]

    with Session(get_engine()) as session:
        saved = session.exec(select(MessageResult)).one()
        assert saved.kind == "tool_results"
        assert saved.message_id == message["id"]
        assert "100000" not in saved.ciphertext and "2026-01" not in saved.ciphertext
        assert decrypt_result_snapshot(saved.ciphertext, saved.key_version)["items"] == result
    history = client.get(url, headers=auth_headers)
    assert history.headers["cache-control"] == "no-store"
    assert history.json()[-1]["tool_results"] == result
    assert history.json()[0]["tool_results"] is None


def test_tool_result_bundle_limits_count_and_rejects_untrusted_kinds():
    one = {"kind": "card_status", "data": {"cards": []}}
    assert len(ToolResultBundle.model_validate({"items": [one] * 8}).items) == 8
    with pytest.raises(ValidationError):
        ToolResultBundle.model_validate({"items": [one] * 9})
    with pytest.raises(ValidationError):
        ToolResultBundle.model_validate({"items": [{"kind": "transfer_completed", "data": {}}]})
    with pytest.raises(ValidationError):
        ToolResultBundle.model_validate({"items": [{"kind": "card_status",
            "data": {"cards": [], "account_token": "forged"}}]})
