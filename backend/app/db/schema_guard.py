"""Shared schema contract for the additive Agent chat tables.

This belongs to the application boundary: startup must not silently alter
an existing database before the operator can back it up and inspect drift.
"""
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

CHAT_TABLES = ("conversationselection", "chatsubmission", "messageresult", "conversationtask")
REQUIRED_BASE = ("user", "conversation", "account", "card", "message", "pendingaction")
VIEW_TABLES = ("uiview", "viewrevision", "viewinteraction", "messageview")
VIEW_REQUIRED_BASE = ("user", "conversation", "message")


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


def view_schema_status(engine: Engine) -> tuple[list[str], list[str]]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [name for name in VIEW_TABLES if name not in existing]
    drift: list[str] = []
    for name in VIEW_TABLES:
        if name not in existing:
            continue
        expected = {column.name for column in SQLModel.metadata.tables[name].columns}
        actual = {column["name"] for column in inspector.get_columns(name)}
        absent = expected - actual
        if absent:
            drift.append(name + ": missing columns " + ",".join(sorted(absent)))

    def primary_key(name: str) -> set[str]:
        return set(inspector.get_pk_constraint(name).get("constrained_columns") or ())

    def foreign_key_exists(name: str, columns: tuple[str, ...],
                           referred_table: str, referred_columns: tuple[str, ...]) -> bool:
        return any(
            tuple(foreign_key.get("constrained_columns") or ()) == columns
            and foreign_key.get("referred_table") == referred_table
            and tuple(foreign_key.get("referred_columns") or ()) == referred_columns
            for foreign_key in inspector.get_foreign_keys(name)
        )

    if "uiview" in existing:
        if not foreign_key_exists("uiview", ("user_id",), "user", ("id",)):
            drift.append("uiview: missing user_id foreign key")
        if not foreign_key_exists("uiview", ("conversation_id",), "conversation", ("id",)):
            drift.append("uiview: missing conversation_id foreign key")
    if "viewrevision" in existing:
        if primary_key("viewrevision") != {"view_id", "revision"}:
            drift.append("viewrevision: missing view_id/revision composite primary key")
        if not foreign_key_exists("viewrevision", ("view_id",), "uiview", ("id",)):
            drift.append("viewrevision: missing view_id foreign key")
    if "viewinteraction" in existing:
        if primary_key("viewinteraction") != {"view_id", "event_id"}:
            drift.append("viewinteraction: missing view_id/event_id composite primary key")
        if not foreign_key_exists(
            "viewinteraction", ("view_id", "result_revision"),
            "viewrevision", ("view_id", "revision"),
        ):
            drift.append("viewinteraction: missing result revision foreign key")
    if "messageview" in existing:
        if primary_key("messageview") != {"message_id"}:
            drift.append("messageview: missing message_id primary key")
        if not foreign_key_exists("messageview", ("message_id",), "message", ("id",)):
            drift.append("messageview: missing message_id foreign key")
        if not foreign_key_exists(
            "messageview", ("view_id", "revision"),
            "viewrevision", ("view_id", "revision"),
        ):
            drift.append("messageview: missing immutable view revision foreign key")
    return missing, drift


def ensure_existing_chat_schema(engine: Engine) -> None:
    """Empty databases may bootstrap; additive chat/view tables need explicit upgrades."""
    if engine.dialect.name != "sqlite":
        return
    existing_tables = set(inspect(engine).get_table_names())
    if not existing_tables:
        return
    chat_missing, chat_drift = chat_schema_status(engine)
    view_missing, view_drift = view_schema_status(engine)
    if chat_missing or chat_drift or view_missing or view_drift:
        issues = []
        instructions = []
        if chat_missing or chat_drift:
            issues.append("chat missing=" + ",".join(chat_missing or ["none"]))
            issues.append("chat drift=" + ";".join(chat_drift or ["none"]))
            instructions.append(
                "'uv run python scripts/check_chat_schema.py' and explicitly confirm '--apply'"
            )
        if view_missing or view_drift:
            issues.append("view missing=" + ",".join(view_missing or ["none"]))
            issues.append("view drift=" + ";".join(view_drift or ["none"]))
            instructions.append(
                "'uv run python scripts/check_generative_ui_schema.py' and explicitly confirm '--apply'"
            )
        raise RuntimeError(
            "已有数据库需要升级或人工核验，已拒绝自动建表（" + "; ".join(issues) +
            "）。先停服务并备份，再在 backend 下运行 " + "；".join(instructions) + "。"
        )
