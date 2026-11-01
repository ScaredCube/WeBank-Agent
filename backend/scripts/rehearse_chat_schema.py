"""Exercise chat schema preflight, upgrade, and rollback on a SYNTHETIC SQLite database.

This CLI intentionally accepts no database path. It creates a fresh legacy
schema in TemporaryDirectory, calls the same production migration helper,
restores the generated backup into ANOTHER temporary file and proves that
the old schema/data survive unchanged.

Never runs against DATABASE_URL. No real financial data, credentials or
LLM calls are used.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import ChatSubmission, Conversation, Message, User
from scripts.check_chat_schema import (
    TARGETS, apply_additive_chat_schema, schema_status,
)


def inspect_integrity(file: Path) -> None:
    with closing(sqlite3.connect(file)) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        db.execute("PRAGMA foreign_keys=ON")
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def snapshot(file: Path) -> dict:
    """Record schema and rows, ignoring only SQLite's non-business internals."""
    inspect_integrity(file)
    with closing(sqlite3.connect(file)) as db:
        schema = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        tables = [name for kind, name, _, _ in schema if kind == "table"]
        rows = {
            name: db.execute('SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid').fetchall()
            for name in tables
        }
        return {"schema": schema, "rows": rows}


def restore_to_new_file(backup: Path, destination: Path) -> None:
    """Restore to a NEW path; never overwrite the database being upgraded."""
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an existing database")
    if not backup.is_file():
        raise FileNotFoundError("Expected a verified backup")
    with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
    inspect_integrity(destination)


def exercise_migration(tmp: Path) -> dict:
    legacy_file = tmp / "synthetic_legacy.sqlite"
    engine = create_engine("sqlite:///" + legacy_file.as_posix())
    old_tables = [table for table in SQLModel.metadata.sorted_tables if table.name not in TARGETS]
    SQLModel.metadata.create_all(engine, tables=old_tables)
    with Session(engine) as db:
        user = User(username="schema_rehearsal_only", password_hash="not-a-real-password",
                    display_name="Synthetic")
        db.add(user)
        db.commit()
        db.refresh(user)
        conversation = Conversation(user_id=user.id, title="Synthetic history")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        db.add(Message(conversation_id=conversation.id, role="user", content="fake placeholder"))
        db.commit()
        user_id, conversation_id = user.id, conversation.id

    initial = snapshot(legacy_file)
    missing, drift = schema_status(engine)
    if set(missing) != set(TARGETS) or drift:
        raise AssertionError("Legacy preflight did not identify all new tables")
    if list(tmp.glob("*.bak")):
        raise AssertionError("Dry-run unexpectedly wrote a backup")
    backup = apply_additive_chat_schema(engine)
    if backup is None or not backup.is_file():
        raise AssertionError("Upgrade failed to produce a backup")
    upgraded_missing, upgraded_drift = schema_status(engine)
    if upgraded_missing or upgraded_drift:
        raise AssertionError("Upgraded schema is not complete")
    if snapshot(backup) != initial:
        raise AssertionError("Backup does not match pre-migration schema/data")

    with Session(engine) as db:
        db.add(ChatSubmission(user_id=user_id, conversation_id=conversation_id,
                              request_id="rehearsal-unique-key", payload_digest="synthetic"))
        db.commit()
    try:
        with Session(engine) as db:
            db.add(ChatSubmission(user_id=user_id, conversation_id=conversation_id,
                                  request_id="rehearsal-unique-key", payload_digest="synthetic"))
            db.commit()
        raise AssertionError("Duplicate request key was accepted")
    except IntegrityError:
        pass

    if apply_additive_chat_schema(engine) is not None:
        raise AssertionError("An already upgraded database was modified")
    if len(list(tmp.glob("*.bak"))) != 1:
        raise AssertionError("Second migration produced an unnecessary backup")
    engine.dispose()

    restored_file = tmp / "restored_legacy.sqlite"
    restore_to_new_file(backup, restored_file)
    if snapshot(restored_file) != initial:
        raise AssertionError("Rollback does not reproduce the original schema/data")
    restored_engine = create_engine("sqlite:///" + restored_file.as_posix())
    restored_missing, restored_drift = schema_status(restored_engine)
    restored_engine.dispose()
    if set(restored_missing) != set(TARGETS) or restored_drift:
        raise AssertionError("Rollback did not restore the original legacy schema")

    return {
        "result": "PASS",
        "scope": "synthetic_temporary_sqlite_only",
        "verified": ["dry_run", "backup", "additive_upgrade", "existing_rows",
                     "unique_request_id", "repeat_upgrade", "rollback_to_separate_file",
                     "schema_and_data_equal", "sqlite_integrity"],
        "production_database_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print concise machine-readable result")
    args = parser.parse_args()
    try:
        with TemporaryDirectory(prefix="bank-agent-schema-rehearsal-") as directory:
            result = exercise_migration(Path(directory))
    except Exception as error:
        print(json.dumps({"result": "FAIL", "error": type(error).__name__},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False) if args.json else
          "SCHEMA_REHEARSAL_PASS: " + ", ".join(result["verified"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
