import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlmodel import Session, SQLModel

from app.models import User
from app.db.schema_guard import VIEW_TABLES
from scripts.check_generative_ui_schema import (
    apply_additive_view_schema, schema_status,
)


def _legacy_chat_database(tmp_path):
    file = tmp_path / "legacy-chat.sqlite3"
    engine = create_engine("sqlite:///" + file.as_posix())
    legacy_tables = [
        table for table in SQLModel.metadata.sorted_tables
        if table.name not in VIEW_TABLES
    ]
    SQLModel.metadata.create_all(engine, tables=legacy_tables)
    with Session(engine) as db:
        db.add(User(username="preserved-view-user", password_hash="hash"))
        db.commit()
    return engine, file


def test_generative_ui_upgrade_is_additive_backed_up_and_idempotent(tmp_path):
    engine, file = _legacy_chat_database(tmp_path)
    missing, drift = schema_status(engine)
    assert missing == list(VIEW_TABLES) and not drift
    assert not list(tmp_path.glob("*.bak"))

    backup = apply_additive_view_schema(engine)
    assert backup is not None and backup.is_file()
    assert schema_status(engine) == ([], [])
    assert set(VIEW_TABLES).issubset(inspect(engine).get_table_names())
    view_fks = inspect(engine).get_foreign_keys("messageview")
    assert any(
        tuple(fk["constrained_columns"]) == ("view_id", "revision")
        and fk["referred_table"] == "viewrevision"
        and tuple(fk["referred_columns"]) == ("view_id", "revision")
        for fk in view_fks
    )

    with sqlite3.connect(file) as upgraded, sqlite3.connect(backup) as preserved:
        assert upgraded.execute(
            "select username from user"
        ).fetchone() == ("preserved-view-user",)
        assert preserved.execute(
            "select username from user"
        ).fetchone() == ("preserved-view-user",)
        preserved_tables = {
            row[0] for row in preserved.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        assert not set(VIEW_TABLES) & preserved_tables

    assert apply_additive_view_schema(engine) is None
    assert len(list(tmp_path.glob("*.bak"))) == 1
    engine.dispose()


def test_generative_ui_schema_drift_refuses_backup_and_modification(tmp_path):
    engine, file = _legacy_chat_database(tmp_path)
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE messageview (message_id INTEGER PRIMARY KEY)")
        db.commit()
    before = set(inspect(engine).get_table_names())
    missing, drift = schema_status(engine)
    assert "messageview" not in missing
    assert any("messageview" in issue for issue in drift)

    with pytest.raises(RuntimeError, match="drift"):
        apply_additive_view_schema(engine)

    assert set(inspect(engine).get_table_names()) == before
    assert not list(tmp_path.glob("*.bak"))
    engine.dispose()
