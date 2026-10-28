from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlalchemy import Index, UniqueConstraint, text

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


class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", unique=True, index=True)
    status: str = "active"
    updated_at: datetime = Field(default_factory=utcnow)


class CardLossRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    status: str = "pending"


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


class PendingAction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    action_type: str
    details_json: str
    risk_level: str
    status: str = "pending"
    token_hash: str
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    confirmed_at: datetime | None = None


class VerificationSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    code_digest: str
    attempts: int = 0
    status: str = "pending"
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    verified_at: datetime | None = None


class TransferRequest(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    idempotency_key: str
    recipient_name: str
    recipient_phone_masked: str | None = None
    recipient_phone_digest: str | None = None
    amount_fen: int
    note: str = ""
    status: str = "pending"
    transaction_id: int | None = Field(default=None, foreign_key="transaction.id")
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class SecurityState(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    failure_count: int = 0
    failure_window_started_at: datetime = Field(default_factory=utcnow)
    locked_until: datetime | None = None
    request_count: int = 0
    request_window_started_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    request_id: str = Field(index=True)
    conversation_id: int | None = Field(default=None, foreign_key="conversation.id", index=True)
    action_id: int | None = Field(default=None, index=True)
    transfer_id: int | None = Field(default=None, index=True)
    transaction_id: int | None = None
    event_type: str = Field(index=True)
    tool: str | None = None
    risk_level: str | None = None
    reason_codes: str | None = None
    result: str | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class DataToken(SQLModel, table=True):
    __table_args__ = (Index("uq_active_account_reference", "user_id", "entity_id", unique=True,
                            sqlite_where=text("kind = 'account' AND revoked_at IS NULL"),
                            postgresql_where=text("kind = 'account' AND revoked_at IS NULL")),)
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True, unique=True)
    kind: str
    entity_id: int | None = None
    ciphertext: str | None = None
    key_version: str | None = None
    digest: str | None = None
    request_scope: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AuditTokenContext(SQLModel, table=True):
    audit_id: int = Field(foreign_key="auditlog.id", primary_key=True)
    reference_id: int | None = None
    entity_kind: str | None = None


class TransferTokenBinding(SQLModel, table=True):
    transfer_id: int = Field(foreign_key="transferrequest.id", primary_key=True)
    source_token_id: int = Field(foreign_key="datatoken.id")
    target_token_id: int | None = Field(default=None, foreign_key="datatoken.id")
    request_scope: str
