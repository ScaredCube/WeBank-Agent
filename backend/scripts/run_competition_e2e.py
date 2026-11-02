"""Local isolated read-only product smoke test (real LLM only with explicit --live).

Starts the current FastAPI + Vite sources on dedicated loopback ports and
creates a temporary synthetic SQLite. Drives a real Chrome browser with the
project's Playwright dependency. It MUST NOT access the existing 8000/5189
services or any non-temporary database. No actual bank payment is possible.
"""
import argparse
from contextlib import closing
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"
BROWSER_SCRIPTS = FRONTEND / "scripts"
DEFAULT_BROWSER_ENTRYPOINT = "scripts/competition_e2e.cjs"
BACKEND_PORT = 8022
FRONTEND_PORT = 5222


def _free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _await_http(url: str, *, processes: list[subprocess.Popen], timeout: float = 35) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError("An isolated child server exited before becoming healthy")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.25)
    raise TimeoutError("Isolated server health check timed out")


def _create_env(database: Path) -> dict[str, str]:
    env = dict(os.environ)
    # Only the synthetic database and its related security configuration are
    # overridden; the existing provider key is read by the backend itself from .env.
    hour = datetime.now(timezone(timedelta(hours=8))).hour
    env.update({
        "DATABASE_URL": "sqlite:///" + database.as_posix(),
        "DEBUG": "true",
        "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "DATA_HMAC_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "JWT_SECRET": base64.urlsafe_b64encode(secrets.token_bytes(40)).decode(),
        "DEMO_USERNAME": "demo",
        "DEMO_PASSWORD": "demo123",
        "RISK_NIGHT_START_HOUR": str((hour + 1) % 24),
        "RISK_NIGHT_END_HOUR": str((hour + 2) % 24),
        "CORS_ORIGINS": f"http://127.0.0.1:{FRONTEND_PORT}",
        "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{BACKEND_PORT}",
    })
    return env


def _database_snapshot(path: Path) -> dict:
    # Run only on the newly created synthetic DB; never includes real bank data.
    import sqlite3
    if not path.is_file():
        raise AssertionError("Synthetic database disappeared")
    with closing(sqlite3.connect(path)) as db:
        account_rows = db.execute(
            "SELECT name,masked_number,balance_fen FROM account ORDER BY id"
        ).fetchall()
        transfers = db.execute("SELECT status,amount_fen,transaction_id FROM transferrequest").fetchall()
        pending_actions = db.execute("SELECT id FROM pendingaction").fetchall()
        preparations = db.execute("SELECT id FROM operationpreparation").fetchall()
        ledger = db.execute(
            "SELECT amount_fen FROM \"transaction\" WHERE category='模拟转账'"
        ).fetchall()
        submission_states = db.execute(
            "SELECT state, COUNT(*) FROM chatsubmission GROUP BY state ORDER BY state"
        ).fetchall()
    return {
        "account_rows": account_rows,
        "transfers": transfers,
        "ledger": ledger,
        "pending_actions": pending_actions,
        "preparations": preparations,
        "submission_states": submission_states,
    }


def _database_summary(path: Path, baseline: dict | None = None) -> dict:
    state = _database_snapshot(path)
    account_rows = state["account_rows"]
    transfers = state["transfers"]
    ledger = state["ledger"]
    pending_actions = state["pending_actions"]
    preparations = state["preparations"]
    submission_states = state["submission_states"]
    # The current demo seed creates TWO accounts. Verify each exact identity
    # and opening balance rather than silently accepting any state drift.
    expected_accounts = [
        ("演示活期账户", "**** 0001", 500000),
        ("零钱账户", "**** 0002", 386012),
    ]
    if account_rows != expected_accounts:
        raise AssertionError("Read-only browser test altered synthetic account state")
    if baseline is not None and account_rows != baseline["account_rows"]:
        raise AssertionError("Read-only browser test changed synthetic account balances")
    if baseline is not None and transfers != baseline["transfers"]:
        raise AssertionError("Read-only browser test changed synthetic transfer status")
    if transfers or ledger or pending_actions or preparations:
        raise AssertionError("Read-only browser test unexpectedly created an operation")
    return {"synthetic_balance_unchanged": True, "transfer_rows": len(transfers),
            "transfer_status_unchanged": baseline is None or transfers == baseline["transfers"],
            "ledger_rows": len(ledger), "pending_action_rows": len(pending_actions),
            "preparation_rows": len(preparations),
            "submission_states": dict(submission_states)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="Explicit opt-in: query configured LLM with synthetic read-only banking")
    parser.add_argument("--evidence-dir", type=Path,
                        help="Optional local QA output directory outside Git")
    parser.add_argument("--browser-entrypoint", default=DEFAULT_BROWSER_ENTRYPOINT,
                        help="Browser script relative to frontend/; must be under frontend/scripts/ (default: %(default)s)")
    args = parser.parse_args()
    if not args.live:
        parser.error("This workflow calls the provider; specify --live explicitly")
    entrypoint = Path(args.browser_entrypoint)
    browser = (FRONTEND / entrypoint).resolve()
    browser_scripts = BROWSER_SCRIPTS.resolve()
    if entrypoint.is_absolute() or not browser.is_relative_to(browser_scripts) or browser.suffix.lower() != ".cjs":
        parser.error("--browser-entrypoint must name a .cjs file under frontend/scripts/")
    if not browser.is_file():
        raise SystemExit("Browser test entrypoint is missing")
    if not all(_free(port) for port in (BACKEND_PORT, FRONTEND_PORT)):
        raise SystemExit("Refusing to touch already occupied isolation ports")
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node or the browser test entrypoint is missing")
    if not (FRONTEND / "node_modules" / "vite" / "bin" / "vite.js").exists():
        raise SystemExit("Frontend dependencies are missing")

    evidence = args.evidence_dir
    if evidence is not None:
        evidence = evidence.resolve()
        if evidence.is_relative_to(REPO):
            raise SystemExit("Screenshots must be stored outside source control")
        evidence.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen] = []
    try:
        with TemporaryDirectory(prefix="bank-agent-comp-e2e-", ignore_cleanup_errors=True) as scratch:
            db = Path(scratch) / "synthetic.sqlite"
            env = _create_env(db)
            env["BANK_AGENT_E2E_OUTPUT"] = str(evidence or Path(scratch))
            # Capture only sanitized child output; never output provider credentials.
            backend = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
                 "--log-level", "error", "--no-access-log"],
                cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(backend)
            vite = subprocess.Popen(
                [node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"),
                 "--host", "127.0.0.1", "--port", str(FRONTEND_PORT), "--strictPort"],
                cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(vite)
            _await_http(f"http://127.0.0.1:{BACKEND_PORT}/api/health", processes=processes)
            _await_http(f"http://127.0.0.1:{FRONTEND_PORT}/login", processes=processes)
            baseline = _database_snapshot(db)
            with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/health",
                                         timeout=5) as health_response:
                model_info = json.load(health_response).get("llm", {})
            if model_info.get("mode") != "openai":
                raise RuntimeError("The isolated service is not using the real model")
            try:
                run = subprocess.run(
                    [node, str(browser), str(evidence or Path(scratch))],
                    cwd=FRONTEND, env=env, capture_output=True, text=True, timeout=420,
                )
            except subprocess.TimeoutExpired as exc:
                captured = []
                for output in (exc.stdout, exc.stderr):
                    if isinstance(output, bytes):
                        output = output.decode("utf-8", errors="replace")
                    if isinstance(output, str):
                        captured.extend(output.splitlines())
                stages = [line.removeprefix("E2E_STAGE ") for line in captured
                          if line.startswith("E2E_STAGE ")]
                stage = stages[-1] if stages else "unknown"
                raise TimeoutError("Browser integration timed out at stage " + stage) from None
            if run.returncode != 0:
                raise RuntimeError("Browser integration failed: " + run.stderr[-1700:]
                                   + " " + run.stdout[-1500:])
            browser = json.loads(run.stdout.strip().splitlines()[-1])
            data = _database_summary(db, baseline)
            result = {"result": "PASS", "scope": "isolated_synthetic_bank",
                      "model": model_info.get("model"), "browser": browser,
                      "database": data, "real_funds_moved": False}
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if evidence:
                (evidence / "summary.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0
    except Exception as exc:
        print(json.dumps({"result": "FAIL", "reason": type(exc).__name__,
                          "detail": str(exc)[-1800:]}, ensure_ascii=False), flush=True)
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
        # Windows SQLite connections cannot be unlinked until child processes exit.
        # The temporary path is locally generated and never accepts user input.
        if 'scratch' in locals() and Path(scratch).exists():
            # On Windows SQLite may retain a closing OS file handle briefly after
            # uvicorn exits. Retry ONLY this freshly created temporary directory.
            for attempt in range(20):
                try:
                    shutil.rmtree(scratch)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)


if __name__ == "__main__":
    raise SystemExit(main())
