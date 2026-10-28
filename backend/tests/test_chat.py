import json
import logging

from app.agent.llm import LLMChunk
from app.agent.registry import RiskLevel, ToolRegistry, ToolSpec


def _sse_payloads(text: str) -> list[dict]:
    payloads = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                payloads.append(json.loads(line[len("data: ") :]))
    return payloads


def test_chat_stream_and_persist(client, auth_headers):
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers)
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "你好，帮我看看这个月的账单"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payloads = _sse_payloads(response.text)
    types = [payload["type"] for payload in payloads]
    assert "delta" in types
    assert types[-1] == "done"

    streamed = "".join(payload["text"] for payload in payloads if payload["type"] == "delta")
    assert "演示模式" in streamed

    messages = client.get(
        f"/api/chat/conversations/{conversation_id}/messages",
        headers=auth_headers,
    ).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["content"] == streamed

    conversations = client.get("/api/chat/conversations", headers=auth_headers).json()
    assert conversations[0]["title"].startswith("你好")


def test_chat_requires_auth(client):
    response = client.get("/api/chat/conversations")
    assert response.status_code == 401


def test_chat_rejects_missing_conversation(client, auth_headers):
    response = client.post(
        "/api/chat/conversations/999/messages",
        json={"content": "hello"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_chat_executes_balance_tool_and_returns_result_to_model(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        seen_result = None

        async def stream(self, messages, tools=None):
            self.calls += 1
            assert {item["function"]["name"] for item in tools} == {
                "get_account_balance", "list_recent_transactions", "get_monthly_bill", "prepare_transfer", "get_card_status", "prepare_card_loss"
            }
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call-1", "type": "function",
                    "function": {"name": "get_account_balance", "arguments": "{}"},
                }])
            else:
                self.seen_result = json.loads(messages[-1]["content"])
                yield LLMChunk(content="你的余额是 999999 元。")

    llm = FakeLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(
        f"/api/chat/conversations/{created['id']}/messages",
        json={"content": "查询余额"}, headers=auth_headers,
    )
    events = _sse_payloads(response.text)
    assert [event["type"] for event in events] == ["delta", "done"]
    assert llm.seen_result["ok"]
    assert llm.seen_result["data"][0]["balance_fen"] == 500000
    assert "5,000.00 元" in events[-1]["message"]["content"]
    assert "999999" not in events[-1]["message"]["content"]


def test_chat_rejects_model_user_id_override(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0
        seen_result = None

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call-1", "type": "function",
                    "function": {"name": "get_account_balance", "arguments": '{"user_id": 2}'},
                }])
            else:
                self.seen_result = json.loads(messages[-1]["content"])
                yield LLMChunk(content="查询参数无效。")

    llm = FakeLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(
        f"/api/chat/conversations/{created['id']}/messages",
        json={"content": "查询余额"}, headers=auth_headers,
    )
    assert response.status_code == 200
    assert llm.seen_result == {"ok": False, "data": None, "error": "查询参数无效"}
    assert "查询参数无效" in _sse_payloads(response.text)[-1]["message"]["content"]


def test_chat_renders_transactions_from_tool_not_model(client, auth_headers, monkeypatch):
    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{
                    "id": "call-1", "type": "function",
                    "function": {"name": "list_recent_transactions",
                                 "arguments": '{"limit": 2}'},
                }])
            else:
                yield LLMChunk(content="交易金额为 123456 元。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(
        f"/api/chat/conversations/{created['id']}/messages",
        json={"content": "查询最近交易"}, headers=auth_headers,
    )
    content = _sse_payloads(response.text)[-1]["message"]["content"]
    assert "购物" in content and "餐饮" in content
    assert "500.00 元" in content
    assert "123456" not in content


def test_chat_stops_repeated_tool_calls(client, auth_headers, monkeypatch):
    class RepeatingLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            yield LLMChunk(tool_calls=[{
                "id": f"call-{self.calls}", "type": "function",
                "function": {"name": "get_account_balance", "arguments": "{}"},
            }])

    llm = RepeatingLLM()
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: llm)
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(
        f"/api/chat/conversations/{created['id']}/messages",
        json={"content": "查询余额"}, headers=auth_headers,
    )
    events = _sse_payloads(response.text)
    assert [event["type"] for event in events] == ["error"]
    assert llm.calls == 4


def test_chat_does_not_display_model_bank_claim_without_tool(client, auth_headers, monkeypatch):
    class HallucinatingLLM:
        async def stream(self, messages, tools=None):
            yield LLMChunk(content="你的余额有一百万，转账已经成功。")

    monkeypatch.setattr("app.agent.loop.get_llm", lambda: HallucinatingLLM())
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(
        f"/api/chat/conversations/{created['id']}/messages",
        json={"content": "查余额"}, headers=auth_headers,
    )
    content = _sse_payloads(response.text)[-1]["message"]["content"]
    assert "一百万" not in content
    assert "转账已经成功" not in content
    assert "未能通过工具完成查询" in content


def test_chat_does_not_execute_yellow_tool(client, auth_headers, monkeypatch, caplog):
    executed = []

    async def handler(**kwargs):
        executed.append(True)
        return {"ok": True, "data": None, "error": None}

    registry = ToolRegistry()
    registry.register(ToolSpec(name="risky", description="测试", parameters={},
                               risk=RiskLevel.YELLOW, handler=handler))

    class FakeLLM:
        calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "call-1", "type": "function",
                                            "function": {"name": "risky", "arguments": "{}"}}])
            else:
                yield LLMChunk(content="操作已成功")

    monkeypatch.setattr("app.agent.loop.create_agent_registry", lambda: registry)
    monkeypatch.setattr("app.agent.loop.get_llm", lambda: FakeLLM())
    caplog.set_level(logging.INFO, logger="app.agent.loop")
    created = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()
    response = client.post(f"/api/chat/conversations/{created['id']}/messages",
                           json={"content": "执行操作"}, headers=auth_headers)
    assert not executed
    assert "操作需要进一步验证" in _sse_payloads(response.text)[-1]["message"]["content"]
    assert any("risk_decision tool=risky" in record.message for record in caplog.records)
