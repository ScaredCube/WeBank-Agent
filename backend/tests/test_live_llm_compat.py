"""Offline regression tests for issues discovered by a live provider integration.
These tests never call any external LLM endpoint.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.llm import LLMChunk, OpenAIProvider, _new_internal_tool_call_id
from app.services.redaction import mask_text


def test_generated_tool_call_ids_do_not_trigger_sensitive_number_masking():
    ids = [_new_internal_tool_call_id() for _ in range(32)]
    assert len(set(ids)) == len(ids)
    assert all(item.startswith("call_") and item[5:].isalpha() for item in ids)
    assert all(mask_text(item) == item for item in ids)


def test_openai_adapter_replaces_vendor_ids_but_preserves_function_arguments():
    vendor_id = "call_1380013800013800138000"
    argument_json = json.dumps({"month": "2026-01"})

    async def chunks():
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None, tool_calls=[SimpleNamespace(
                index=0, id=vendor_id,
                function=SimpleNamespace(name="get_monthly_bill", arguments=argument_json),
            )]),
            finish_reason=None,
        )])
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None, tool_calls=None),
            finish_reason="tool_calls",
        )])

    create = AsyncMock(return_value=chunks())
    provider = object.__new__(OpenAIProvider)
    provider.model = "offline-stub"
    provider._client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create)))

    async def collect():
        return [part async for part in provider.stream(
            [{"role": "user", "content": "simulated"}],
            tools=[{"type": "function", "function": {"name": "get_monthly_bill"}}],
        )]

    output = asyncio.run(collect())
    assert output[-1].finish_reason == "tool_calls"
    actual = output[-1].tool_calls[0]
    assert actual["id"] != vendor_id
    assert mask_text(actual["id"]) == actual["id"]
    assert actual["function"]["name"] == "get_monthly_bill"
    assert json.loads(actual["function"]["arguments"]) == {"month": "2026-01"}


def test_selected_account_is_bound_server_side_for_bill_even_when_model_forges_token(
    client, auth_headers, monkeypatch,
):
    from app.agent import loop as agent_loop

    class WrongTokenLLM:
        mode = "openai"
        def __init__(self):
            self.calls = 0

        async def stream(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield LLMChunk(tool_calls=[{"id": "call_safelettersonly", "type": "function",
                    "function": {"name": "get_monthly_bill", "arguments": json.dumps({
                        "month": "2026-01", "account_token": "model_invented_token"
                    })}}])
            else:
                yield LLMChunk(content="查询结束")

    monkeypatch.setattr(agent_loop, "get_llm", lambda: WrongTokenLLM())
    account_id = client.get("/api/bank/accounts", headers=auth_headers).json()[0]["account_id"]
    conversation_id = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    url = f"/api/chat/conversations/{conversation_id}/messages"

    response = client.post(url, json={
        "content": "查询这个模拟账户 2026-01 的账单",
        "references": [{"kind": "account", "id": account_id}],
    }, headers=auth_headers)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert any(event["type"] == "bill_result" for event in events)
    history = client.get(url, headers=auth_headers).json()
    assert history[-1]["bill_result"]["month"] == "2026-01"

    # The exact same forged model token cannot access an account without an
    # authenticated selection. The model never gets to grant its own authority.
    other_conversation = client.post("/api/chat/conversations", json={}, headers=auth_headers).json()["id"]
    wrong = client.post(f"/api/chat/conversations/{other_conversation}/messages",
        json={"content": "查询模拟账户 2026-01 账单"},
        headers=auth_headers)
    assert wrong.status_code == 200
    wrong_events = [json.loads(line[6:]) for line in wrong.text.splitlines() if line.startswith("data: ")]
    assert not any(event["type"] == "bill_result" for event in wrong_events)
