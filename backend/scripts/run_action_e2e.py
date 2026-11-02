"""Real browser + Agent on an isolated synthetic SQLite, with explicit --live.

The browser may confirm ONE test-only transfer of 100 fen. This runner refuses
occupied ports, uses fresh ephemeral secrets and never touches existing bank data.
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

from run_competition_e2e import (
    BACKEND, BACKEND_PORT, FRONTEND, FRONTEND_PORT,
    _await_http, _create_env, _free,
)

BROWSER = FRONTEND / "scripts" / "competition_action_e2e.cjs"


def verify_synthetic_database(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as db:
        accounts = db.execute(
            "SELECT name,balance_fen FROM account ORDER BY id"
        ).fetchall()
        transfers = db.execute(
            "SELECT status,amount_fen,transaction_id FROM transferrequest"
        ).fetchall()
        actions = db.execute(
            "SELECT status,risk_level FROM pendingaction"
        ).fetchall()
        ledger = db.execute(
            'SELECT amount_fen FROM "transaction" WHERE category=?',
            ("模拟转账",),
        ).fetchall()
        audits = [row[0] for row in db.execute(
            "SELECT event_type FROM auditlog"
        ).fetchall()]
    assert accounts == [
        ("演示活期账户", 499900), ("零钱账户", 386012),
    ], "Synthetic account balances did not match exactly one 1-CNY transfer"
    assert len(transfers) == 1 and transfers[0][:2] == ("completed", 100)
    assert transfers[0][2] is not None
    assert actions == [("completed", "yellow")]
    assert ledger == [(100,)]
    assert "action_confirmed" in audits and "transfer_completed" in audits
    return {"accounts_verified": 2, "completed_transfers": 1,
            "transfer_amount_fen": 100, "ledger_rows": len(ledger),
            "audit_confirmed": True, "audit_completed": True}



def verify_synthetic_edit_database(
    database: Path, *, risk_level: str = 'yellow', face_required: bool = False,
) -> dict:
    """Old action must be cancelled; only the new 2-yuan transfer is executed."""
    with closing(sqlite3.connect(database)) as db:
        accounts = db.execute("SELECT name,balance_fen FROM account ORDER BY id").fetchall()
        transfers = db.execute(
            "SELECT t.status,t.amount_fen,t.transaction_id,a.status,a.risk_level "
            "FROM transferrequest t JOIN pendingaction a ON a.id=t.action_id ORDER BY t.id"
        ).fetchall()
        ledger = db.execute(
            'SELECT amount_fen FROM "transaction" WHERE category=?', ("模拟转账",)
        ).fetchall()
        events = [r[0] for r in db.execute("SELECT event_type FROM auditlog")]
        face_details = [json.loads(row[0]).get('verification') for row in db.execute(
            "SELECT details_json FROM pendingaction ORDER BY id"
        )]
        verification_rows = db.execute(
            "SELECT status,attempts FROM verificationsession ORDER BY action_id"
        ).fetchall()
    assert accounts == [("演示活期账户", 499800), ("零钱账户", 386012)], (
        "Only the edited 2-yuan action may change the synthetic account"
    )
    assert len(transfers) == 2, "Expected exactly two independent prepared actions"
    first, second = transfers
    assert first[0] == "pending" and first[1] == 100 and first[2] is None
    assert first[3:] == ("cancelled", risk_level), "First action was not cancelled"
    assert second[0] == "completed" and second[1] == 200 and second[2] is not None
    assert second[3:] == ("completed", risk_level), "Edited action not completed"
    assert ledger == [(200,)], "Old cancelled transfer must have no ledger entry"
    assert "action_cancelled" in events
    assert ("verification_succeeded" if risk_level == 'red' else "action_confirmed") in events
    if risk_level == 'red':
        assert 'verification_started' in events, 'Red action did not start verification'
        assert 'verification_failed' in events, 'Incorrect code was not rejected'
    if face_required:
        assert face_details == ['password_face', 'password_face'], 'Face gate not recorded in both actions'
        assert verification_rows == [('verified', 1)], 'Final action not face-verified after one failed code'
        assert events.count('verification_succeeded') >= 2, 'Code and face must be separate verification steps'
        assert events.count('guard_denied') == 2, 'Synthetic Guard escalation did not occur twice'
    assert "transfer_completed" in events
    return {"actions": 2, "cancelled": 1, "completed": 1,
            "only_executed_amount_fen": 200, "ledger_rows": len(ledger),
            "original_action_not_executed": True,
            "face_required_and_verified": face_required}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true",
                      help="Real model + synthetic action: explicitly opt in")
    mode.add_argument("--fixture", action="store_true",
                      help="Deterministic model + real Agent/Chrome/synthetic SQLite")
    parser.add_argument("--diagnose", action="store_true",
                        help="Live-only sanitized tool-shape trace; no argument values")
    parser.add_argument('--backend-port', type=int, default=BACKEND_PORT)
    parser.add_argument('--frontend-port', type=int, default=FRONTEND_PORT)
    parser.add_argument('--face', action='store_true',
                        help='Synthetic Guard escalation: require red code + face')
    parser.add_argument('--red', action='store_true',
                        help='Test-only simulated night-time red transfer verification')
    parser.add_argument('--edit', action='store_true',
                        help='Exercise cancel, edit and prepare a new synthetic transfer')
    args = parser.parse_args()
    if args.edit and not args.fixture:
        parser.error('--edit currently requires --fixture')
    if args.red and not (args.fixture and args.edit):
        parser.error('--red requires --fixture --edit')
    if args.face and not (args.fixture and args.edit and args.red):
        parser.error('--face requires --fixture --edit --red')
    browser_entry = (FRONTEND / 'scripts' / 'competition_action_edit_e2e.cjs') if args.edit else BROWSER
    if args.diagnose and not args.live:
        parser.error("--diagnose requires --live")
    if not browser_entry.is_file():
        raise SystemExit("Action browser entrypoint missing")
    node = shutil.which("node")
    if not node or not (FRONTEND / "node_modules" / "vite" / "bin" / "vite.js").exists():
        raise SystemExit("Frontend Node dependencies unavailable")
    if any(not (1024 <= port <= 65535) for port in (args.backend_port, args.frontend_port)) or args.backend_port == args.frontend_port:
        parser.error('isolation ports must be distinct and within 1024..65535')
    if not all(_free(port) for port in (args.backend_port, args.frontend_port)):
        raise SystemExit("Dedicated isolated ports occupied")
    processes = []
    try:
        with TemporaryDirectory(prefix="bank-agent-action-e2e-", ignore_cleanup_errors=True) as scratch:
            database = Path(scratch) / "only-synthetic.sqlite"
            env = _create_env(database)
            env['CORS_ORIGINS'] = f'http://127.0.0.1:{args.frontend_port}'
            env['VITE_API_PROXY_TARGET'] = f'http://127.0.0.1:{args.backend_port}'
            env['BANK_AGENT_ACTION_E2E_BASE'] = f'http://127.0.0.1:{args.frontend_port}'
            if args.fixture:
                # Startup requires a provider; fixture mode injects a
                # deterministic tool model and never makes a real network call.
                env["LLM_API_KEY"] = "synthetic-action-e2e-no-call"
                env["REPLY_GROUNDING_ENABLED"] = "false"
            if args.face:
                env['BANK_AGENT_ACTION_E2E_FACE'] = '1'
            if args.red:
                # Force only the ephemeral test process into its red night window.
                # Runs quickly; fail closed if the local hour changes midway.
                hour = datetime.now(timezone(timedelta(hours=8))).hour
                env['RISK_NIGHT_START_HOUR'] = str(hour)
                env['RISK_NIGHT_END_HOUR'] = str((hour + 1) % 24)
                env['BANK_AGENT_ACTION_E2E_RED'] = '1'
            if args.diagnose:
                env["BANK_AGENT_ACTION_TRACE"] = str(Path(scratch) / "shape.jsonl")
            backend_entry = ("scripts.action_fixture_server:app" if args.fixture
                             else "scripts.action_trace_server:app" if args.diagnose
                             else "app.main:app")
            backend = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", backend_entry,
                 "--host", "127.0.0.1", "--port", str(args.backend_port),
                 "--log-level", "error", "--no-access-log"],
                cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(backend)
            vite = subprocess.Popen(
                [node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"),
                 "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"],
                cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(vite)
            _await_http(f"http://127.0.0.1:{args.backend_port}/api/health", processes=processes)
            _await_http(f"http://127.0.0.1:{args.frontend_port}/login", processes=processes)
            import urllib.request
            with urllib.request.urlopen(
                f"http://127.0.0.1:{args.backend_port}/api/health", timeout=5
            ) as response:
                model = json.load(response).get("llm", {})
            expected_mode = "openai"
            if model.get("mode") != expected_mode:
                raise RuntimeError("Unexpected model mode in isolated Agent E2E")
            browser = subprocess.run(
                [node, str(browser_entry)], cwd=FRONTEND, env=env,
                capture_output=True, text=True, timeout=190,
            )
            if browser.returncode:
                with closing(sqlite3.connect(database)) as db:
                    counters = {
                        "prepared": db.execute("SELECT COUNT(*) FROM transferrequest").fetchone()[0],
                        "actions": db.execute("SELECT COUNT(*) FROM pendingaction").fetchone()[0],
                        "events": [dict(type=r[0],tool=r[1],result=r[2],reason=r[3]) for r in db.execute("SELECT event_type,tool,result,reason_codes FROM auditlog").fetchall()],
                    }
                trace = Path(scratch) / "shape.jsonl"
                safe_trace = [json.loads(line) for line in trace.read_text(
                    encoding="utf-8").splitlines()] if trace.exists() else []
                raise RuntimeError(
                    "Browser action flow failed: "
                    + (browser.stderr[-450:] or browser.stdout[-450:])
                    + " | Synthetic-only counters: " + json.dumps(counters)
                    + " | Tool shape: " + json.dumps(safe_trace)
                )
            screen_result = json.loads(browser.stdout.strip().splitlines()[-1])
            if screen_result.get("result") != "PASS":
                raise AssertionError("Browser did not confirm the action")
            verified = (verify_synthetic_edit_database(
                database, risk_level='red' if args.red else 'yellow', face_required=args.face
            ) if args.edit
                        else verify_synthetic_database(database))
            print(json.dumps({
                "result": "PASS", "scope": "isolated_synthetic_only",
                "model_mode": "deterministic_fixture" if args.fixture else "live_provider",
                "model": model.get("model"), "browser": screen_result,
                "database": verified, "real_funds_moved": False,
            }, ensure_ascii=False), flush=True)
            return 0
    except Exception as exc:
        print(json.dumps({"result": "FAIL", "reason": type(exc).__name__,
                          "detail": str(exc)[-900:]}, ensure_ascii=False), flush=True)
        return 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
