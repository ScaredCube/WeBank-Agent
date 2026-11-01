from datetime import date, datetime

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


class ChatSubmission(SQLModel, table=True):
    """Deduplicates one client-authored Agent request across SSE retries.

    Only a SHA256 payload fingerprint and message/action IDs are persisted;
    no raw request text, confirmation token, API credential or bank token.
    """
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    request_id: str = Field(max_length=64)
    payload_digest: str
    state: str = "processing"
    user_message_id: int | None = Field(default=None, foreign_key="message.id")
    assistant_message_id: int | None = Field(default=None, foreign_key="message.id")
    pending_action_id: int | None = Field(default=None, foreign_key="pendingaction.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ConversationSelection(SQLModel, table=True):
    """Last explicitly selected read-only bank object; never a payment mandate.

    IDs contain no authorization tokens. Every use must re-check the owning
    account/card state in the current authenticated user's session.
    """
    conversation_id: int = Field(foreign_key="conversation.id", primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    account_id: int = Field(foreign_key="account.id")
    card_id: int | None = Field(default=None, foreign_key="card.id")
    updated_at: datetime = Field(default_factory=utcnow)


class MessageResult(SQLModel, table=True):
    """Encrypted server-authored read-only banking snapshot associated with a reply."""
    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id", unique=True, index=True)
    kind: str
    ciphertext: str
    key_version: str
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


class Contact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    bank_name: str
    masked_phone: str
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


class WealthProduct(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: str
    risk_level: str
    expected_rate_bps: int = Field(ge=0)
    term_days: int = Field(default=0, ge=0)
    min_amount_fen: int = Field(gt=0)
    status: str = "available"
    created_at: datetime = Field(default_factory=utcnow)


class WealthHolding(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    product_id: int = Field(foreign_key="wealthproduct.id", index=True)
    amount_fen: int = Field(default=0, ge=0)
    yesterday_earnings_fen: int = Field(default=0, ge=0)
    status: str = "active"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class WealthOrder(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    product_id: int = Field(foreign_key="wealthproduct.id", index=True)
    holding_id: int | None = Field(default=None, foreign_key="wealthholding.id")
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    idempotency_key: str
    order_type: str
    amount_fen: int = Field(gt=0)
    note: str = ""
    status: str = "pending"
    transaction_id: int | None = Field(default=None, foreign_key="transaction.id")
    balance_after_fen: int | None = None
    holding_after_fen: int | None = None
    account_token_id: int = Field(foreign_key="datatoken.id")
    product_token_id: int = Field(foreign_key="datatoken.id")
    request_scope: str
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class WealthRiskProfile(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    risk_level: str = "R1"
    score: int = Field(default=0, ge=0, le=9)
    assessed_at: datetime = Field(default_factory=utcnow)


class Subscription(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    merchant: str = Field(index=True)
    amount_fen: int = Field(gt=0)
    cycle: str = "monthly"
    next_charge_date: date
    status: str = "active"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SubscriptionCancelRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    subscription_id: int = Field(foreign_key="subscription.id", index=True)
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    status: str = "pending"


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


class OperationPreparation(SQLModel, table=True):
    """Additive receipt/binding for card loss and subscription cancellation."""
    __table_args__ = (UniqueConstraint("user_id", "operation", "idempotency_key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    operation: str
    idempotency_key: str
    entity_id: int
    action_id: int = Field(foreign_key="pendingaction.id", unique=True, index=True)
    reference_id: int = Field(foreign_key="datatoken.id")
    request_scope: str
