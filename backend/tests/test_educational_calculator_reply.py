"""A calculator result may support an explanation, never validate bank actions."""
import json

from app.agent.llm import LLMChunk
from app.core.config import settings


def _events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_explanation_survives_a_verified_calculator_call(
    client, auth_headers, monkeypatch,
):
    class Explainer:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call_compoundcalc", "type": "function",
                    "function": {
                        "name": "calculate", "arguments": '{"expression":"100*1.05**2"}',
                    },
                }])
            else:
                yield LLMChunk(content="复利计算原理已说明，具体结果以工具为准。")

    model = Explainer()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "解释一下复利原理，再举个例子"}, headers=auth_headers,
    ))
    assert model.calls == 2
    assert events[-1]["type"] == "done"
    answer = events[-1]["message"]["content"]
    assert answer == "复利计算原理已说明，具体结果以工具为准。"


def test_calculator_cannot_authorize_unverified_bank_action(
    client, auth_headers, monkeypatch,
):
    class BadExplainer:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call_safe_calc", "type": "function",
                    "function": {
                        "name": "calculate", "arguments": '{"expression":"100+5"}',
                    },
                }])
            else:
                yield LLMChunk(content="转账已成功完成。")

    model = BadExplainer()
    monkeypatch.setattr(settings, "reply_grounding_enabled", True)
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    events = _events(client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "解释一下复利是什么"}, headers=auth_headers,
    ))
    assert events[-1]["type"] == "error"
    assert "转账成功" not in str(events)
    assert "action_required" not in [e["type"] for e in events]
