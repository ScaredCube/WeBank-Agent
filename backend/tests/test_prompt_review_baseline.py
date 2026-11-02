"""Detect silent changes to the user-reviewed effective Prompt versions."""
import json
from pathlib import Path

from app.agent.prompt_assembly import (
    assemble_agent_prompt, assemble_guard_prompt, assemble_recovery_prompt,
)
from scripts.review_prompts import extract_literals, manifest_for_source, runtime_versions

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/prompt-reviews/current-manifest.json"
PROMPTS = ROOT / "backend/app/agent/prompts.py"


def test_snapshot_covers_all_effective_prompt_roles_and_validated_intents():
    baseline = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = runtime_versions()
    assert actual == baseline["effective_versions"], (
        "生效 Prompt 版本已变化：请生成 Before/After 和 UX/安全评审后更新基线"
    )
    assert set(actual) == {
        "agent", "guard", "recovery", "tools",
        "reply_policy", "recovery_policy", "read_completion", "grounded_summary",
        "compound_read_summary", "read_result_recovery", "scope_contract", "snapshot_contract",
        "chat_request_recovery", "agent_loop",
        "agent:transfer", "agent:internal_transfer", "agent:collect",
        "agent:purchase", "agent:redeem", "agent:convert",
    }


def test_static_prompt_literals_match_reviewed_baseline():
    text = PROMPTS.read_text(encoding="utf-8")
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["static_prompts"]
    assert manifest_for_source(text) == expected
    assert set(extract_literals(text)) == {
        "SYSTEM_PROMPT", "GUARD_SYSTEM_PROMPT", "RESPONSE_RECOVERY_PROMPT",
    }


def test_manifest_records_actual_assembly_not_a_separate_prompt_copy():
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))["effective_versions"]
    assert assemble_agent_prompt().version == current["agent"]
    assert assemble_guard_prompt().version == current["guard"]
    assert assemble_recovery_prompt().version == current["recovery"]


def test_ast_extraction_does_not_evaluate_untrusted_source():
    harmless = chr(10).join((
        "SYSTEM_PROMPT = 'A'",
        "GUARD_SYSTEM_PROMPT = 'B'",
        "RESPONSE_RECOVERY_PROMPT = 'C'",
    ))
    assert set(extract_literals(harmless)) == {
        "SYSTEM_PROMPT", "GUARD_SYSTEM_PROMPT", "RESPONSE_RECOVERY_PROMPT",
    }
