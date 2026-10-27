from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    display_name: str = "用户"
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str = "新对话"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str
    content: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    masked_number: str
    currency: str = "CNY"
    balance_fen: int = Field(ge=0)
    status: str = "active"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    reference: str = Field(index=True, unique=True)
    direction: str
    amount_fen: int = Field(gt=0)
    balance_after_fen: int = Field(ge=0)
    counterparty: str
    category: str
    note: str = ""
    occurred_at: datetime = Field(default_factory=utcnow, index=True)
