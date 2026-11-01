from collections.abc import Iterator
from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    from app import models  # noqa: F401
    from app.db.schema_guard import ensure_existing_chat_schema

    engine = get_engine()
    # Do not silently create missing Agent chat tables in an existing database.
    # A truly empty database can bootstrap for local synthetic development.
    ensure_existing_chat_schema(engine)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def session_scope() -> Session:
    return Session(get_engine())
