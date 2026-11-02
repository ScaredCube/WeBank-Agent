"""Focused contracts for the extracted Tool execution boundary."""
import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.agent.registry import RiskLevel, ToolExecutionMode, ToolRegistry, ToolSpec
from app.agent.tool_executor import ToolExecutor, VerifiedToolContext
from app.tools.register import create_agent_registry


def test_prepare_operations_are_explicitly_typed_without_changing_model_tool_schema():
    registry = create_agent_registry()
    names = {
        "prepare_transfer", "prepare_card_loss", "prepare_wealth_subscribe",
        "prepare_wealth_redeem", "prepare_cancel_subscription",
        "prepare_internal_transfer", "prepare_collection", "prepare_wealth_convert",
    }
    definitions = registry.definitions()
    for name in names:
        spec = registry.get(name)
        assert spec is not None and spec.execution is ToolExecutionMode.PREPARE
        assert "execution" not in spec.to_openai_schema()["function"]
    assert all(
        registry.get(item["function"]["name"]).execution is ToolExecutionMode.STANDARD
        for item in definitions if item["function"]["name"] not in names
    )


def test_pending_confirmation_token_is_a_client_event_not_model_observation(monkeypatch):
    monkeypatch.setattr("app.agent.tool_executor.record_separately", lambda **kwargs: None)

    async def prepare(*, user_id, amount_fen):
        assert user_id == 3 and amount_fen == 100
        return {
            "ok": True, "action": {"id": 8, "status": "pending"},
            "confirmation_token": "one-shot-secret",
            "transfer_id": 9,
        }

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="prepare_transfer", description="test",
        parameters={"type": "object", "properties": {"amount_fen": {"type": "integer"}},
                    "required": ["amount_fen"], "additionalProperties": False},
        risk=RiskLevel.YELLOW, handler=prepare, execution=ToolExecutionMode.PREPARE,
    ))
    call = {
        "id": "call_safe_1", "type": "function",
        "function": {"name": "prepare_transfer", "arguments": json.dumps({"amount_fen": 100})},
    }
    outcome = asyncio.run(ToolExecutor(registry, None).execute(
        call, VerifiedToolContext(user_id=3), [],
    ))
    assert outcome.stop_reason == "waiting_approval"
    assert outcome.observation is None
    assert len(outcome.events) == 1
    assert outcome.events[0].type == "action_required"
    assert outcome.events[0].data["confirmation_token"] == "one-shot-secret"


def test_prepared_operation_already_executed_has_verified_observation(monkeypatch):
    monkeypatch.setattr("app.agent.tool_executor.record_separately", lambda **kwargs: None)

    async def prepare(*, user_id, amount_fen):
        return {"ok": True, "executed": True, "result_kind": "internal_transfer",
                "result": {"transfer_id": 11}, "transfer_id": 11}

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="prepare_internal_transfer", description="test",
        parameters={"type": "object", "properties": {"amount_fen": {"type": "integer"}},
                    "required": ["amount_fen"], "additionalProperties": False},
        risk=RiskLevel.YELLOW, handler=prepare, execution=ToolExecutionMode.PREPARE,
    ))
    outcome = asyncio.run(ToolExecutor(registry, None).execute(
        {"id": "call_safe_2", "type": "function",
         "function": {"name": "prepare_internal_transfer", "arguments": '{"amount_fen":100}'}},
        VerifiedToolContext(user_id=3), [],
    ))
    assert outcome.stop_reason is None
    assert outcome.observation == {"ok": True, "data": {"transfer_id": 11}, "error": None}
    assert [event.type for event in outcome.events] == ["operation_result"]
    assert "confirmation_token" not in json.dumps(outcome.observation)


@pytest.mark.parametrize(
    "trusted_metadata, expected_metadata",
    [
        ({"account_id": 41}, {"account_id": 41}),
        ({"account_id": True}, None),
        ({"account_id": 41, "source": "client"}, None),
    ],
)
def test_bill_source_metadata_is_internal_event_only(
    monkeypatch, trusted_metadata, expected_metadata,
):
    class FakeSession:
        def commit(self):
            pass

    @contextmanager
    def fake_session_scope():
        yield FakeSession()

    monkeypatch.setattr("app.agent.tool_executor.record_separately", lambda **kwargs: None)
    monkeypatch.setattr("app.agent.tool_executor.record", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent.tool_executor.session_scope", fake_session_scope)
    monkeypatch.setattr(
        "app.agent.tool_executor.assess_tool",
        lambda spec: SimpleNamespace(level=RiskLevel.GREEN, reasons=()),
    )

    bill = {"month": "2026-10", "consumption_fen": 8600}

    async def get_bill(*, session, user_id, month):
        assert user_id == 9 and month == "2026-10"
        return {"ok": True, "data": bill,
                "_trusted_metadata": trusted_metadata, "error": None}

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="get_monthly_bill", description="test",
        parameters={"type": "object", "properties": {"month": {"type": "string"}},
                    "required": ["month"], "additionalProperties": False},
        risk=RiskLevel.GREEN, handler=get_bill,
    ))
    outcome = asyncio.run(ToolExecutor(registry, None).execute(
        {"id": "call_bill_1", "type": "function", "function": {
            "name": "get_monthly_bill", "arguments": '{"month":"2026-10"}'}},
        VerifiedToolContext(user_id=9), [],
    ))

    assert outcome.observation == {"ok": True, "data": bill, "error": None}
    assert "account_id" not in json.dumps(outcome.observation)
    assert len(outcome.events) == 1
    assert outcome.events[0].type == "bill_result"
    expected_event = {"data": bill}
    if expected_metadata is not None:
        expected_event["trusted_metadata"] = expected_metadata
    assert outcome.events[0].data == expected_event
