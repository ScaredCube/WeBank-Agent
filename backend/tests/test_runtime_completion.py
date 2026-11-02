"""End-to-end proof that a bill result does not swallow a second user goal."""
import json

from app.agent.llm import LLMChunk


def _events(response):
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_bill_then_subscription_detection_continues_agent_loop(client, auth_headers, monkeypatch):
    class TwoGoalModel:
        calls = 0
        saw_verified_bill = False

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call_billabc", "type": "function",
                    "function": {
                        "name": "get_monthly_bill",
                        "arguments": '{"month":"2026-01"}',
                    },
                }])
            elif self.calls == 2:
                bill_observation = json.loads(messages[-1]["content"])
                self.saw_verified_bill = (
                    bill_observation.get("ok")
                    and bill_observation["data"]["month"] == "2026-01"
                )
                yield LLMChunk(tool_calls=[{
                    "id": "call_subsabc", "type": "function",
                    "function": {
                        "name": "detect_subscriptions", "arguments": "{}",
                    },
                }])
            else:
                assert messages[-1]["role"] == "tool"
                yield LLMChunk(content="两项核查已完成。")

    model = TwoGoalModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers)
    cid = created.json()["id"]
    response = client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers,
        json={"content": "查询 2026-01 月账单，并检查可能的重复订阅"},
    )
    events = _events(response)
    assert model.calls == 3
    assert model.saw_verified_bill
    assert [event["type"] for event in events if event["type"] != "ui_status"] == ["bill_result", "delta", "done"]
    saved = events[-1]["message"]
    assert saved["bill_result"]["month"] == "2026-01"
    assert saved["content"] == "两项核查已完成。"


def test_server_original_request_prevents_fake_fast_completion(
    client, auth_headers, monkeypatch,
):
    class ExtraGoalModel:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                # The first clause looks like a simple query; the second is
                # user content and must not be truncated away at the delimiter.
                yield LLMChunk(tool_calls=[{
                    "id": "call_billxyz", "type": "function",
                    "function": {
                        "name": "get_monthly_bill",
                        "arguments": '{"month":"2026-01"}',
                    },
                }])
            else:
                yield LLMChunk(content="还需核对订阅。")

    model = ExtraGoalModel()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: model)
    cid = client.post(
        "/api/chat/conversations", json={}, headers=auth_headers,
    ).json()["id"]
    content = "请查账单" + chr(10) * 2 + "[备注]" + chr(10) + "再检查订阅"
    response = client.post(
        f"/api/chat/conversations/{cid}/messages",
        headers=auth_headers, json={"content": content},
    )
    events = _events(response)
    assert model.calls == 2
    assert events[-1]["type"] == "done"
