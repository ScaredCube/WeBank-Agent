"""Crash-restart rehearsal with actual separate Python processes and temporary SQLite.

The worker hard-exits after a committed simulated bank operation. A new Python
process then starts the actual FastAPI application and verifies persisted states.
NEVER accepts an arbitrary database path; no TokenDance calls or real credentials.
"""
import argparse
from contextlib import closing
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

SCENARIOS = ("uncommitted", "pending", "confirmed", "executed")
REQUEST_ID = "req-process-crash-rehearsal-01"
QUESTION = "请先准备一笔1元模拟转账供核对"


def _safe_database() -> Path:
    value = os.environ.get("BANK_AGENT_REHEARSAL_DB")
    if not value:
        raise RuntimeError("Only the parent rehearsal may start child processes")
    path = Path(value).resolve()
    if (not path.parent.name.startswith("bank-agent-process-rehearsal-")
            or path.name not in ("uncommitted.sqlite", "pending.sqlite", "confirmed.sqlite", "executed.sqlite")
            or path.suffix != ".sqlite"):
        raise RuntimeError("Refusing database outside a synthetic rehearsal workspace")
    return path


def _safe_env(database: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("LLM_", "TOKEN", "OPENAI_", "ANTHROPIC_")):
            env.pop(key, None)
    env.update({
        "BANK_AGENT_REHEARSAL_DB": str(database),
        "DATABASE_URL": "sqlite:///" + database.as_posix(),
        "LLM_API_KEY": "", "JWT_SECRET": "synthetic-test-rehearsal-secret-123456",
        "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"r" * 32).decode(),
        "DATA_HMAC_KEY": base64.urlsafe_b64encode(b"h" * 32).decode(),
        "DEMO_USERNAME": "rehearsal_user",
        "DEMO_PASSWORD": "only-synthetic-test-password",
        "DEBUG": "true",
    })
    return env


def _worker(scenario: str) -> None:
    _safe_database()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from datetime import datetime, timezone

    from sqlmodel import Session, SQLModel, select
    from app.core.config import settings
    from app.db.session import get_engine
    from app.db.seed import seed_demo_user, seed_demo_accounts, seed_demo_cards
    from app.models import Account, Conversation
    from app.services.chat_submissions import claim_submission, fingerprint
    from app.schemas.transfers import PrepareTransferRequest
    from app.services.transfer_service import prepare_transfer, execute_transfer
    from app.services.action_service import confirm_pending_action

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = seed_demo_user(session)
        seed_demo_accounts(session, user)
        seed_demo_cards(session, user)
        conversation = Conversation(user_id=user.id, title="Synthetic failure test")
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        account = session.exec(select(Account).where(Account.user_id == user.id)).one()
        user_id, conversation_id, account_id = user.id, conversation.id, account.id
        claim_submission(session, user_id=user_id, conversation_id=conversation_id,
                         request_id=REQUEST_ID, payload_digest=fingerprint(QUESTION, []))

    if scenario == "uncommitted":
        # Terminate with a real SQLite transaction open; the next process
        # must observe SQLite's rollback of the uncommitted debit.
        with closing(sqlite3.connect(_safe_database())) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE account SET balance_fen=balance_fen-100 WHERE id=?",
                               (account_id,))
            print(json.dumps({"scenario": scenario, "conversation_id": conversation_id,
                              "request_id": REQUEST_ID}), flush=True)
            os._exit(87)

    hour = datetime.now(timezone(timedelta(hours=8))).hour
    settings.risk_night_start_hour = (hour + 1) % 24
    settings.risk_night_end_hour = (hour + 2) % 24
    result = prepare_transfer(user_id, PrepareTransferRequest(
        account_id=account_id, recipient_name="合成收款人",
        recipient_phone="13812345678", amount_fen=100,
        idempotency_key="process-crash-rehearsal-key",
    ))
    if scenario in ("confirmed", "executed"):
        with Session(engine) as session:
            if not confirm_pending_action(session, user_id=user_id,
                                          action_id=result["action_id"],
                                          token=result["confirmation_token"]):
                raise RuntimeError("Synthetic confirmation was refused")
    if scenario == "executed":
        execute_transfer(user_id, result["transfer_id"])
    # Only public identifiers in output. The confirmation token never leaves worker.
    print(json.dumps({"scenario": scenario, "conversation_id": conversation_id,
                      "request_id": REQUEST_ID, "transfer_id": result["transfer_id"],
                      "action_id": result["action_id"], "account_id": account_id}), flush=True)
    os._exit(87)  # Emulate an abrupt worker death, skipping teardown and HTTP replies.


def _restart(scenario: str) -> dict:
    _safe_database()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from fastapi.testclient import TestClient
    from sqlmodel import Session, select
    from app.main import app
    from app.db.session import get_engine
    from app.models import Account, ChatSubmission, PendingAction, Transaction, TransferRequest

    # The parent ages ONLY the isolated in-flight row to simulate worker loss.
    # Starting TestClient triggers the application's normal stale recovery.
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={
            "username": "rehearsal_user", "password": "only-synthetic-test-password"})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        with Session(get_engine()) as session:
            submission = session.exec(select(ChatSubmission)).one()
            conv = submission.conversation_id
        status_url = f"/api/chat/conversations/{conv}/requests/{REQUEST_ID}"
        status = client.get(status_url, headers=headers)
        assert status.status_code == 200 and status.json()["state"] == "interrupted"
        assert status.json()["message"] is None
        assert "confirmation_token" not in status.text
        same_request = client.post(f"/api/chat/conversations/{conv}/messages",
            headers=headers, json={"content": QUESTION, "request_id": REQUEST_ID})
        assert same_request.status_code == 409

        if scenario == "uncommitted":
            with Session(get_engine()) as session:
                assert session.exec(select(Account)).one().balance_fen == 500000
                assert not session.exec(select(TransferRequest)).all()
                assert not session.exec(select(PendingAction)).all()
                assert not session.exec(select(Transaction).where(
                    Transaction.category == "模拟转账")).all()
                assert session.exec(select(ChatSubmission)).one().state == "interrupted"
            return {"scenario": scenario, "crash_exit_code": 87, "restart": "PASS",
                    "duplicate_chat_request": "blocked", "transaction_count": 0,
                    "unexpected_balance_change": False}

        with Session(get_engine()) as session:
            account = session.exec(select(Account)).one()
            transfer = session.exec(select(TransferRequest)).one()
            action = session.get(PendingAction, transfer.action_id)
            original_balance = 500000
            assert transfer.amount_fen == 100
            assert action.status == scenario if scenario != "executed" else action.status == "completed"
            if scenario == "pending":
                assert account.balance_fen == original_balance
            elif scenario == "confirmed":
                assert account.balance_fen == original_balance
            else:
                assert account.balance_fen == original_balance - 100
            action_id = action.id
            transfer_id = transfer.id

        # Restart does not grant any confirmation, even to the account owner.
        info = client.get(f"/api/actions/{action_id}", headers=headers)
        assert info.status_code == 200 and "confirmation_token" not in info.text
        # Reissuing the same idempotency key is a lookup, never a new pending
        # operation, and must not re-disclose the one-time confirmation token.
        repeated_prepare = client.post("/api/transfers/prepare", headers=headers, json={
            "account_id": account.id, "recipient_name": "合成收款人",
            "recipient_phone": "13812345678", "amount_fen": 100,
            "idempotency_key": "process-crash-rehearsal-key",
        })
        assert repeated_prepare.status_code == 200, repeated_prepare.text
        assert repeated_prepare.json()["transfer_id"] == transfer_id
        assert repeated_prepare.json()["confirmation_token"] is None
        if scenario == "pending":
            assert client.post(f"/api/transfers/{transfer_id}/execute",
                               headers=headers).status_code == 400
        elif scenario == "confirmed":
            # A new explicit authenticated request is still required to execute.
            # Here we deliberately test that action once, then replay it safely.
            first = client.post(f"/api/transfers/{transfer_id}/execute", headers=headers)
            assert first.status_code == 200
            again = client.post(f"/api/transfers/{transfer_id}/execute", headers=headers)
            assert again.status_code == 200 and first.json() == again.json()
        else:
            # Worker committed before crash; retry merely returns the saved receipt.
            first = client.post(f"/api/transfers/{transfer_id}/execute", headers=headers)
            assert first.status_code == 200
            again = client.post(f"/api/transfers/{transfer_id}/execute", headers=headers)
            assert again.status_code == 200 and first.json() == again.json()

        with Session(get_engine()) as session:
            transfers = session.exec(select(TransferRequest)).all()
            ledger = session.exec(select(Transaction).where(
                Transaction.category == "模拟转账")).all()
            account = session.exec(select(Account)).one()
            assert len(transfers) == 1
            assert len(ledger) == (0 if scenario == "pending" else 1)
            assert account.balance_fen == (500000 if scenario == "pending" else 499900)
            assert transfers[0].status == ("pending" if scenario == "pending" else "completed")
            assert session.exec(select(ChatSubmission)).one().state == "interrupted"
    return {"scenario": scenario, "crash_exit_code": 87, "restart": "PASS",
            "duplicate_chat_request": "blocked", "transaction_count": len(ledger),
            "unexpected_balance_change": False}


def _age_only_synthetic_submission(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("UPDATE chatsubmission SET updated_at = '2020-01-01 00:00:00.000000'"
                     " WHERE request_id = ?", (REQUEST_ID,))
        conn.commit()


def _parent() -> dict:
    report = []
    script = str(Path(__file__).resolve())
    with TemporaryDirectory(prefix="bank-agent-process-rehearsal-") as directory:
        for scenario in SCENARIOS:
            db = Path(directory) / f"{scenario}.sqlite"
            env = _safe_env(db)
            child = subprocess.run([sys.executable, script, "--internal-worker", scenario],
                                   cwd=str(Path(__file__).resolve().parents[1]), env=env,
                                   capture_output=True, text=True, timeout=35)
            if child.returncode != 87:
                raise RuntimeError("Synthetic worker did not die at expected crash point: " +
                                   child.stderr[-800:])
            if child.stdout.count('"scenario"') != 1:
                raise RuntimeError("Synthetic worker did not report a durable preparation")
            _age_only_synthetic_submission(db)
            restarted = subprocess.run([sys.executable, script, "--internal-restart", scenario],
                                        cwd=str(Path(__file__).resolve().parents[1]), env=env,
                                        capture_output=True, text=True, timeout=35)
            if restarted.returncode != 0:
                raise RuntimeError("Restart validation failed: " + restarted.stderr[-1000:])
            report.append(json.loads(restarted.stdout))
    return {"result": "PASS", "scope": "isolated_synthetic_processes",
            "scenarios": report, "production_data_modified": False,
            "live_llm_calls": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--internal-worker", choices=SCENARIOS, help=argparse.SUPPRESS)
    mode.add_argument("--internal-restart", choices=SCENARIOS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.internal_worker:
        _worker(args.internal_worker)
        return 1
    if args.internal_restart:
        print(json.dumps(_restart(args.internal_restart)), flush=True)
        return 0
    try:
        print(json.dumps(_parent(), ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"result": "FAIL", "error_type": type(error).__name__,
                          "details": str(error)[-1000:]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
