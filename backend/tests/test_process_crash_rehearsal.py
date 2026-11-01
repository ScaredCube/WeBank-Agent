"""Verify true process termination/restart, on synthetic temporary SQLite only."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.rehearse_agent_process_crash import _safe_database


def test_worker_crash_recovery_does_not_double_prepare_or_debit():
    script = Path(__file__).resolve().parents[1] / "scripts" / "rehearse_agent_process_crash.py"
    run = subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parents[1], capture_output=True, text=True, timeout=110,
    )
    assert run.returncode == 0, run.stderr[-600:] + run.stdout[-1000:]
    report = json.loads(run.stdout)
    assert report["result"] == "PASS"
    assert report["scope"] == "isolated_synthetic_processes"
    assert report["production_data_modified"] is False
    assert report["live_llm_calls"] == 0
    assert [stage["scenario"] for stage in report["scenarios"]] == [
        "uncommitted", "pending", "confirmed", "executed",
    ]
    assert [stage["transaction_count"] for stage in report["scenarios"]] == [0, 0, 1, 1]
    assert all(stage["crash_exit_code"] == 87 and stage["restart"] == "PASS"
               and stage["duplicate_chat_request"] == "blocked"
               and not stage["unexpected_balance_change"]
               for stage in report["scenarios"])


@pytest.mark.parametrize("value", [
    "D:/competition/WeBank-Agent/backend/bank_agent.db",
    "C:/Users/Public/real_bank_agent.sqlite",
    "C:/Temp/bank-agent-process-rehearsal-pretend/../../real_bank_agent.sqlite",
])
def test_rehearsal_cannot_point_child_at_arbitrary_database(monkeypatch, value):
    monkeypatch.setenv("BANK_AGENT_REHEARSAL_DB", value)
    with pytest.raises(RuntimeError, match="Refusing database"):
        _safe_database()


def test_rehearsal_requires_parent_created_database_location(monkeypatch):
    monkeypatch.delenv("BANK_AGENT_REHEARSAL_DB", raising=False)
    with pytest.raises(RuntimeError, match="Only the parent"):
        _safe_database()
