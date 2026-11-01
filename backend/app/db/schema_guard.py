"""Shared schema contract for the additive Agent chat tables.

This belongs to the application boundary: startup must not silently alter
an existing database before the operator can back it up and inspect drift.
"""
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

CHAT_TABLES = ("conversationselection", "chatsubmission", "messageresult")
REQUIRED_BASE = ("user", "conversation", "account", "card", "message", "pendingaction")


def chat_schema_status(engine: Engine) -> tuple[list[str], list[str]]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [name for name in CHAT_TABLES if name not in existing]
    drift: list[str] = []
    for name in CHAT_TABLES:
        if name not in existing:
            continue
        expected = {column.name for column in SQLModel.metadata.tables[name].columns}
        actual = {column["name"] for column in inspector.get_columns(name)}
        absent = expected - actual
        if absent:
            drift.append(name + ": missing columns " + ",".join(sorted(absent)))

    def unique_columns(name: str) -> list[set[str]]:
        return [
            set(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints(name)
        ] + [
            set(index.get("column_names") or ())
            for index in inspector.get_indexes(name) if index.get("unique")
        ]

    if "chatsubmission" in existing:
        if {"user_id", "request_id"} not in unique_columns("chatsubmission"):
            drift.append("chatsubmission: missing user_id/request_id UNIQUE constraint")
    if "messageresult" in existing:
        if {"message_id"} not in unique_columns("messageresult"):
            drift.append("messageresult: missing message_id UNIQUE constraint")
    return missing, drift


def ensure_existing_chat_schema(engine: Engine) -> None:
    """Empty databases may bootstrap; existing SQLite must be upgraded first."""
    if engine.dialect.name != "sqlite":
        return
    existing_tables = set(inspect(engine).get_table_names())
    if not existing_tables:
        return
    missing, drift = chat_schema_status(engine)
    if missing or drift:
        issues = "; ".join(
            (["missing=" + ",".join(missing)] if missing else [])
            + (["drift=" + ";".join(drift)] if drift else [])
        )
        raise RuntimeError(
            "已有数据库需要升级或人工核验，已拒绝自动建表（" + issues +
            "）。先停服务并备份，再在 backend 下运行 "
            "'uv run python scripts/check_chat_schema.py'，"
            "确认后显式执行 '--apply'。"
        )
