"""Shared SQLite write boundary and preparation identity; never commits for callers."""
import hashlib
import re
import secrets

from sqlalchemy import text
from sqlmodel import Session, select

from app.models import DataToken, OperationPreparation
from app.services.action_service import get_pending_action
from app.services.audit_service import record, request_context
from app.services.vault import VaultError, resolve


def begin_write(session: Session, error_type: type[Exception], message: str) -> None:
    if session.get_bind().dialect.name != "sqlite":
        raise error_type(message)
    # Must precede any read: rechecks, changes, receipts and success audit share
    # this lock and commit. Session.close rolls back on exceptions.
    session.execute(text("BEGIN IMMEDIATE"))


def agent_preparation_key(operation: str) -> str:
    # Only server request context determines identity; the model cannot choose
    # a key or evade deduplication by changing arguments / tool-call IDs.
    scope = request_context.get()
    if scope is None:
        return secrets.token_urlsafe(24)
    return hashlib.sha256(f"{scope}:{operation}".encode()).hexdigest()


def find_preparation(session: Session, user_id: int, operation: str,
                     key: str | None, entity_id: int, error_type: type[Exception]) -> dict | None:
    if key is None:
        return None
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", key):
        raise error_type("请求编号无效")
    receipt = session.exec(select(OperationPreparation).where(
        OperationPreparation.user_id == user_id, OperationPreparation.operation == operation,
        OperationPreparation.idempotency_key == key)).first()
    if receipt is None:
        return None
    if receipt.entity_id != entity_id:
        raise error_type("请求编号已用于其他操作")
    action = get_pending_action(session, user_id=user_id, action_id=receipt.action_id)
    if action is None or action["action_type"] != operation:
        raise error_type("待处理动作不可用")
    record(session, user_id=user_id, action_id=receipt.action_id,
           event_type="operation_prepare_retried", result="retry")
    return {"action_id": receipt.action_id, "confirmation_token": None,
            "status": action["status"]}


def bind_preparation(session: Session, user_id: int, operation: str, key: str | None,
                     entity_id: int, action_id: int, token: str, scope: str) -> None:
    reference = session.exec(select(DataToken).where(
        DataToken.user_id == user_id, DataToken.token == token)).one()
    session.add(OperationPreparation(
        user_id=user_id, operation=operation, idempotency_key=key or secrets.token_urlsafe(24),
        entity_id=entity_id, action_id=action_id, reference_id=reference.id, request_scope=scope))
    session.flush()


def check_prepared_reference(session: Session, user_id: int, operation: str,
                             action_id: int, entity_id: int, kind: str,
                             reference_entity_id: int) -> None:
    receipt = session.exec(select(OperationPreparation).where(
        OperationPreparation.user_id == user_id, OperationPreparation.operation == operation,
        OperationPreparation.action_id == action_id)).first()
    if receipt is None or receipt.entity_id != entity_id:
        raise VaultError()
    reference = session.get(DataToken, receipt.reference_id)
    if (reference is None or resolve(session, user_id, reference.token, kind,
                                     receipt.request_scope) != reference_entity_id):
        raise VaultError()
