"""A full authenticated chat turn uses an independent read synthesizer."""
import json

from app.agent.llm import LLMChunk
from app.core.config import settings


def _events(response):
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_verified_bill_analysis_is_synthesized_and_persisted(
    client, auth_headers, monkeypatch,
):
    monkeypatch.setattr(settings, "generative_ui_enabled", False)

    class Model:
        mode = "openai"
        turns = []
        async def stream(self, messages, tools=None):
            self.turns.append({"messages": messages, "tools": bool(tools)})
            if tools:
                yield LLMChunk(tool_calls=[{
                    "id": "call_v2_bill", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": '{"month":"2026-01"}'},
                }])
            else:
                yield LLMChunk(content=json.dumps({
                    "narrative": "本次已取得月度收支及分类数据，可以从消费分布开始分析，但不能仅凭账单判断变化的真正原因。"
                }, ensure_ascii=False))

    model = Model()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post("/api/chat/conversations", headers=auth_headers, json={}).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": "帮我分析2026-01的账单与消费分类"},
    ))
    assert len(model.turns) == 2
    assert model.turns[0]["tools"] is True
    assert model.turns[1]["tools"] is False
    assert model.turns[1]["messages"][0]["role"] == "system"
    assert events[-1]["type"] == "done"
    reply = events[-1]["message"]["content"]
    assert reply.startswith("本次已取得月度收支")
    assert "2026-01 月度账单" in reply
    assert events[-1]["message"]["bill_result"]["month"] == "2026-01"
    saved = client.get(f"/api/chat/conversations/{cid}/messages",
                       headers=auth_headers).json()
    assert saved[-1]["content"] == reply
