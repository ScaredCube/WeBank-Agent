"""User-bound data references. All methods operate in the caller's transaction."""
import base64
import hashlib
import hmac
import json
import secrets
import string
from datetime import timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from app.core.config import settings
from app.core.time import utcnow
from app.models import Account, AuditTokenContext, DataToken
from app.services.audit_service import record


class VaultError(Exception):
    def __init__(self):
        super().__init__("引用不可用")


def _random_reference() -> str:
    return "".join(secrets.choice(string.ascii_letters) for _ in range(32))


def _keys() -> tuple[dict[str, str], str]:
    try:
        previous = json.loads(settings.data_encryption_previous_keys)
        if not isinstance(previous, dict) or not settings.data_encryption_key_version:
            raise ValueError()
        keys = {**previous, settings.data_encryption_key_version: settings.data_encryption_key}
        current = settings.data_encryption_key
        hmac_key = base64.urlsafe_b64decode(settings.data_hmac_key.encode())
        current_raw = base64.urlsafe_b64decode(current.encode())
        if (len(hmac_key) != 32 or len(current_raw) != 32 or current_raw == hmac_key
                or current_raw == settings.jwt_secret.encode() or hmac_key == settings.jwt_secret.encode()):
            raise ValueError()
        for version, key in keys.items():
            if not isinstance(version, str) or not version or not isinstance(key, str):
                raise ValueError()
            Fernet(key.encode())
            raw = base64.urlsafe_b64decode(key.encode())
            if raw == hmac_key or raw == settings.jwt_secret.encode():
                raise ValueError()
        return keys, settings.data_hmac_key
    except Exception:
        raise VaultError() from None


def _audit(session: Session, user_id: int, event: str, row: DataToken | None, result: str) -> None:
    entry = record(session, user_id=user_id, event_type=event, result=result,
                   reason_code="reference_unavailable" if result == "denied" else None)
    session.add(AuditTokenContext(audit_id=entry.id, reference_id=row.id if row else None,
                                  entity_kind=row.kind if row else None))
    session.flush()


def create_temporary(session: Session, user_id: int, kind: str, value: str, scope: str) -> str:
    if kind not in {"phone_input", "card_input"} or not value or not scope:
        raise VaultError()
    keys, hmac_key = _keys()
    token = f"<{('PHONE_TMP' if kind == 'phone_input' else 'CARD_INPUT')}_{_random_reference()}>"
    body = json.dumps({"token": token, "user_id": user_id, "kind": kind, "value": value}, separators=(",", ":"))
    ciphertext = Fernet(keys[settings.data_encryption_key_version].encode()).encrypt(body.encode()).decode()
    digest = hmac.new(base64.urlsafe_b64decode(hmac_key), value.encode(), hashlib.sha256).hexdigest()
    row = DataToken(user_id=user_id, token=token, kind=kind, ciphertext=ciphertext,
                    key_version=settings.data_encryption_key_version, digest=digest,
                    request_scope=scope, expires_at=utcnow() + timedelta(minutes=10))
    session.add(row); session.flush()
    return token


def create_account_token(session: Session, user_id: int, account_id: int) -> str:
    account = session.exec(select(Account).where(Account.id == account_id, Account.user_id == user_id,
                                                 Account.status == "active")).first()
    if account is None:
        raise VaultError()
    row = session.exec(select(DataToken).where(DataToken.user_id == user_id, DataToken.kind == "account",
                            DataToken.entity_id == account_id, DataToken.revoked_at.is_(None))).first()
    if row is None:
        row = DataToken(user_id=user_id, kind="account", entity_id=account_id,
                        token=f"<CARD_{_random_reference()}>")
        session.add(row); session.flush()
    return row.token


def resolve(session: Session, user_id: int, token: str, expected_kind: str, scope: str) -> int | str:
    row = session.exec(select(DataToken).where(DataToken.token == token, DataToken.user_id == user_id)).first()
    now = utcnow()
    expiry = row.expires_at if row else None
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if (row is None or row.kind != expected_kind or row.revoked_at is not None
            or (expiry is not None and expiry <= now)
            or (row.request_scope is not None and row.request_scope != scope)):
        _audit(session, user_id, "token_resolve_denied", None, "denied")
        raise VaultError()
    if row.kind == "account":
        account = session.exec(select(Account).where(Account.id == row.entity_id, Account.user_id == user_id,
                                                     Account.status == "active")).first()
        if account is None:
            _audit(session, user_id, "token_resolve_denied", None, "denied")
            raise VaultError()
        value = account.id
    else:
        try:
            keys, _ = _keys()
            body = json.loads(Fernet(keys[row.key_version].encode()).decrypt(row.ciphertext.encode()).decode())
            if body.get("token") != row.token or body.get("user_id") != user_id or body.get("kind") != row.kind:
                raise ValueError()
            value = body["value"]
            if not isinstance(value, str):
                raise ValueError()
            if row.key_version != settings.data_encryption_key_version:
                row.ciphertext = Fernet(keys[settings.data_encryption_key_version].encode()).encrypt(
                    json.dumps(body, separators=(",", ":")).encode()).decode()
                row.key_version = settings.data_encryption_key_version
                session.add(row)
        except (InvalidToken, KeyError, ValueError, TypeError, AttributeError, VaultError):
            _audit(session, user_id, "token_resolve_denied", None, "denied")
            raise VaultError() from None
    _audit(session, user_id, "token_resolved", row, "success")
    return value


def revoke(session: Session, user_id: int, token: str) -> None:
    row = session.exec(select(DataToken).where(DataToken.token == token, DataToken.user_id == user_id,
                                               DataToken.revoked_at.is_(None))).first()
    if row is None:
        _audit(session, user_id, "token_resolve_denied", None, "denied")
        raise VaultError()
    row.revoked_at = utcnow(); session.add(row)
    _audit(session, user_id, "token_revoked", row, "success")
