"""Check or create the additive Agent chat and read-task tables (SQLite).

Dry-run by default. --apply requires an existing SQLite file, makes a backup
using sqlite3.backup, then creates ONLY missing tables. Existing schema drift
fails closed. This is migration preparation, not a full Alembic migration.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import models  # noqa: E402,F401
from app.db.session import get_engine  # noqa: E402
from app.db.schema_guard import (  # noqa: E402
    CHAT_TABLES as TARGETS, REQUIRED_BASE as REQUIRED_EXISTING,
    chat_schema_status as schema_status,
)


def backup_sqlite_file(engine: Engine) -> Path:
    filename = engine.url.database
    if engine.dialect.name != "sqlite" or not filename or filename == ":memory:":
        raise RuntimeError("Apply only supports an existing on-disk SQLite database")
    source = Path(filename).resolve()
    if not source.is_file():
        raise RuntimeError("SQLite database does not exist: refusing to create a new one")
    name = source.name + ".pre-chat-schema-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + ".bak"
    backup = source.with_name(name)
    try:
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(backup)) as dst:
            src.backup(dst)
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    return backup


def apply_additive_chat_schema(engine: Engine) -> Path | None:
    missing, drift = schema_status(engine)
    if drift:
        raise RuntimeError("Existing schema drift: " + "; ".join(drift))
    if not missing:
        return None
    existing = set(inspect(engine).get_table_names())
    required_missing = sorted(set(REQUIRED_EXISTING) - existing)
    if required_missing:
        raise RuntimeError("Missing required base tables: " + ", ".join(required_missing))
    backup = backup_sqlite_file(engine)
    for name in missing:
        SQLModel.metadata.tables[name].create(bind=engine, checkfirst=True)
    remaining, drift = schema_status(engine)
    if remaining or drift:
        raise RuntimeError("Schema verification failed after creation; backup=" + str(backup))
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Back up existing SQLite file and add missing tables")
    args = parser.parse_args()
    engine = get_engine()
    missing, drift = schema_status(engine)
    print("CHAT_SCHEMA", "missing=" + ",".join(missing or ["none"]),
          "drift=" + ";".join(drift or ["none"]))
    if drift:
        return 2
    if args.apply:
        backup = apply_additive_chat_schema(engine)
        print("CHAT_SCHEMA_APPLIED", "unchanged" if backup is None else "backup=" + str(backup))
        return 0
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
