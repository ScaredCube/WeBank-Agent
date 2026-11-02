"""Isolated live Agent shape diagnostics. Only writes booleans / enums.
No bank references, names, phone numbers, provider text or credentials are recorded.
"""
import json
import os
from pathlib import Path

from app.main import app
from app.agent.tool_executor import ToolExecutor
from app.risk.injection import validate_tool_arguments
from app.services.redaction import mask_value

original_execute = ToolExecutor.execute
_ALLOWED_FIELDS = frozenset({
    "source_token", "target_token", "recipient_contact_token",
    "recipient_name", "amount_fen", "note",
})

async def traced_execute(self, call, context, prior_calls):
    fn = call.get("function", {})
    name = fn.get("name")
    if name != "prepare_transfer":
        return await original_execute(self, call, context, prior_calls)
    raw = fn.get("arguments", "")
    try:
        args = json.loads(raw)
    except (TypeError, ValueError):
        args = None
    schema_error = validate_tool_arguments(self.registry.get(name), args) if isinstance(args, dict) else "invalid"
    observation = {
        "tool": "prepare_transfer",
        "json_object": isinstance(args, dict),
        "known_fields": sorted(k for k in args if k in _ALLOWED_FIELDS) if isinstance(args, dict) else [],
        "unknown_field_count": sum(k not in _ALLOWED_FIELDS for k in args) if isinstance(args, dict) else None,
        "amount_type": type(args.get("amount_fen")).__name__ if isinstance(args, dict) else None,
        "amount_matches_request": args.get("amount_fen") == 100 if isinstance(args, dict) and type(args.get("amount_fen")) is int else False,
        "recipient_name_type": type(args.get("recipient_name")).__name__ if isinstance(args, dict) else None,
        "contains_sensitive_plaintext": mask_value(args) != args if isinstance(args, dict) else None,
        "redacted_field_names": sorted(
            k for k, v in args.items() if k in _ALLOWED_FIELDS and mask_value(v) != v
        ) if isinstance(args, dict) else [],
        "prior_denied_calls": sum(":denied" in call for call in prior_calls),
        "schema_valid": schema_error is None,
        "explicit_account_verified": context.verified_account_token is not None,
        "intent_action_present": context.intent_action is not None,
    }
    try:
        outcome = await original_execute(self, call, context, prior_calls)
        observation["tool_success"] = bool(outcome.observation and outcome.observation.get("ok")) or bool(outcome.stop_reason == "waiting_approval")
        observation["waiting_approval"] = outcome.stop_reason == "waiting_approval"
        return outcome
    finally:
        trace_path = os.environ.get("BANK_AGENT_ACTION_TRACE")
        if trace_path:
            with Path(trace_path).open("a", encoding="utf-8") as f:
                f.write(json.dumps(observation, sort_keys=True) + "\n")

ToolExecutor.execute = traced_execute
