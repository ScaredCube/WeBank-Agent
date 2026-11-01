"""Offline migration preparedness: dry-run, verified backup and schema drift."""
import sqlite3
from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, create_engine
from app.models import User

from scripts.check_chat_schema import apply_additive_chat_schema, schema_status, TARGETS


def _old_database(tmp_path):
    file = tmp_path / "original.sqlite3"
    engine = create_engine("sqlite:///" + file.as_posix())
    existing_tables = [
        table for table in SQLModel.metadata.sorted_tables
        if table.name not in TARGETS
    ]
    SQLModel.metadata.create_all(engine, tables=existing_tables)
    return engine, file


def test_additive_chat_upgrade_preserves_existing_data_and_backs_up(tmp_path):
    engine, file = _old_database(tmp_path)
    with Session(engine) as db:
        db.add(User(username="retained_user", password_hash="hash", display_name="retained"))
        db.commit()
    missing, drift = schema_status(engine)
    assert sorted(missing) == sorted(TARGETS) and not drift
    assert not list(tmp_path.glob("*.bak"))  # dry-run never creates files

    backup = apply_additive_chat_schema(engine)
    assert backup and backup.is_file()
    assert schema_status(engine) == ([], [])
    with sqlite3.connect(file) as upgraded, sqlite3.connect(backup) as preserved:
        assert upgraded.execute("select username from user").fetchone() == ("retained_user",)
        assert preserved.execute("select username from user").fetchone() == ("retained_user",)
        assert "chatsubmission" not in {
            row[0] for row in preserved.execute("select name from sqlite_master where type='table'")
        }
    assert apply_additive_chat_schema(engine) is None
    assert len(list(tmp_path.glob("*.bak"))) == 1
    assert "chatsubmission" in inspect(engine).get_table_names()
    engine.dispose()


def test_schema_drift_refuses_to_migrate_or_modify_database(tmp_path):
    engine, file = _old_database(tmp_path)
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE chatsubmission (id INTEGER PRIMARY KEY)")
        db.commit()
    missing, drift = schema_status(engine)
    assert "conversationselection" in missing and drift
    try:
        apply_additive_chat_schema(engine)
        assert False, "Existing schema drift should never be silently changed"
    except RuntimeError as err:
        assert "drift" in str(err).lower()
    assert not list(tmp_path.glob("*.bak"))
    engine.dispose()
