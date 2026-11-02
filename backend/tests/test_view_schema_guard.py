import pytest
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from app.db.schema_guard import ensure_existing_chat_schema


VIEW_TABLE_NAMES = {"uiview", "viewrevision", "viewinteraction", "messageview"}


def test_existing_chat_database_missing_view_tables_fails_before_auto_creation(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "legacy.sqlite3").as_posix())
    legacy_tables = [
        table for table in SQLModel.metadata.sorted_tables
        if table.name not in VIEW_TABLE_NAMES
    ]
    SQLModel.metadata.create_all(engine, tables=legacy_tables)
    before = set(inspect(engine).get_table_names())

    with pytest.raises(RuntimeError, match="view|视图|generative"):
        ensure_existing_chat_schema(engine)

    assert set(inspect(engine).get_table_names()) == before
    engine.dispose()
