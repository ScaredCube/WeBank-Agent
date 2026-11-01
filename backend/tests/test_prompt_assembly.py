"""Focused prompt-assembly contract tests; no model or database calls."""
import pytest

from app.agent.prompt_assembly import assemble_agent_prompt, assemble_guard_prompt
from app.agent.prompts import SYSTEM_PROMPT, GUARD_SYSTEM_PROMPT


def test_base_prompt_is_unchanged_and_version_stable():
    first = assemble_agent_prompt()
    second = assemble_agent_prompt()
    assert first.model_messages() == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert first.version == second.version
    assert first.version.startswith("agent:")


@pytest.mark.parametrize(("intent", "tool"), [
    ("transfer", "prepare_transfer"),
    ("internal_transfer", "prepare_internal_transfer"),
    ("collect", "prepare_collection"),
    ("purchase", "prepare_wealth_subscribe"),
    ("redeem", "prepare_wealth_redeem"),
    ("convert", "prepare_wealth_convert"),
])
def test_validated_intent_directive_preserves_existing_language(intent, tool):
    result = assemble_agent_prompt(verified_intent_action=intent)
    messages = result.model_messages()
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert len(messages) == 2
    assert tool in messages[1]["content"]
    assert "服务端已校验" in messages[1]["content"]
    assert result.version != assemble_agent_prompt().version


def test_unknown_intent_cannot_become_arbitrary_system_message():
    with pytest.raises(ValueError):
        assemble_agent_prompt(verified_intent_action="ignore_previous_instructions")


def test_guard_prompt_is_separate_and_snapshot_is_not_mutable_by_caller():
    guard = assemble_guard_prompt()
    assert guard.model_messages() == [{"role": "system", "content": GUARD_SYSTEM_PROMPT}]
    assert guard.version.startswith("guard:")
    messages = guard.model_messages()
    messages[0]["content"] = "tampered"
    assert guard.model_messages()[0]["content"] == GUARD_SYSTEM_PROMPT
