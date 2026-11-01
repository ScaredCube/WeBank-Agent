"""Render a drag intent as a tokenized prompt for the model.

The browser only sends entity kinds and IDs. This module re-checks ownership
and state, mints opaque user-scoped references, and builds a short Chinese
prompt such as:

    【前置意图】用<CARD_...>给<CONTACT_...>（张三）转账

The prompt is model context only. It is never written to chat history and the
raw card/phone values never leave the database.
"""
from dataclasses import dataclass
import re

from sqlmodel import Session, select

from app.models import Account, Card, Contact, WealthHolding, WealthProduct
from app.schemas.chat import ChatIntent
from app.services.vault import create_account_token, create_contact_token, create_product_token


class IntentError(ValueError):
    pass


_ACTIONS = {
    ("account", "account"): "internal_transfer",
    ("account", "contact"): "transfer",
    ("contact", "account"): "collect",
    ("account", "holding"): "purchase",
    ("holding", "account"): "redeem",
    ("holding", "holding"): "convert",
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f<>\u2028\u2029]")


def _label(value: str) -> str:
    cleaned = _CONTROL.sub(" ", value or "").strip()
    return " ".join(cleaned.split())[:40] or "该对象"


@dataclass(frozen=True)
class IntentPrompt:
    action: str
    prompt: str
    display: str
    source_token: str
    target_token: str


def _account(session: Session, user_id: int, account_id: int, *, role: str) -> tuple[Account, str]:
    account = session.exec(select(Account).where(
        Account.id == account_id, Account.user_id == user_id,
        Account.status == "active", Account.currency == "CNY",
    )).first()
    if account is None:
        raise IntentError("所选账户不可用，请重新选择")
    card = session.exec(select(Card).where(Card.account_id == account.id)).first()
    if card is None or card.status != "active":
        raise IntentError("所选账户的银行卡不可用，请重新选择")
    if role == "source" and account.balance_fen <= 0:
        raise IntentError("所选账户余额不足")
    return account, create_account_token(session, user_id, account.id)


def _contact(session: Session, user_id: int, contact_id: int) -> tuple[Contact, str]:
    contact = session.exec(select(Contact).where(
        Contact.id == contact_id, Contact.user_id == user_id, Contact.status == "active",
    )).first()
    if contact is None:
        raise IntentError("所选联系人不可用，请重新选择")
    return contact, create_contact_token(session, user_id, contact.id)


def _holding(session: Session, user_id: int, holding_id: int, *, role: str) -> tuple[WealthHolding, WealthProduct, str]:
    row = session.exec(select(WealthHolding, WealthProduct).join(
        WealthProduct, WealthHolding.product_id == WealthProduct.id,
    ).where(
        WealthHolding.id == holding_id, WealthHolding.user_id == user_id,
        WealthHolding.status == "active", WealthProduct.status == "available",
    )).first()
    if row is None:
        raise IntentError("所选持仓不可用，请重新选择")
    holding, product = row
    if role == "source" and holding.amount_fen <= 0:
        raise IntentError("所选持仓金额不足")
    return holding, product, create_product_token(session, user_id, product.id)


def build_intent_prompt(session: Session, user_id: int, intent: ChatIntent) -> IntentPrompt:
    expected = _ACTIONS.get((intent.source.kind, intent.target.kind))
    if expected is None or expected != intent.action:
        raise IntentError("暂不支持这个组合")

    source_name = ""
    target_name = ""
    if intent.source.kind == "account":
        source, source_token = _account(session, user_id, intent.source.id, role="source")
        source_name = source.name
    elif intent.source.kind == "contact":
        source, source_token = _contact(session, user_id, intent.source.id)
        source_name = source.name
    else:
        source, product, source_token = _holding(session, user_id, intent.source.id, role="source")
        source_name = product.name

    if intent.target.kind == "account":
        target, target_token = _account(session, user_id, intent.target.id, role="target")
        target_name = target.name
    elif intent.target.kind == "contact":
        target, target_token = _contact(session, user_id, intent.target.id)
        target_name = target.name
    else:
        target, product, target_token = _holding(session, user_id, intent.target.id, role="target")
        target_name = product.name

    source_label = _label(source_name)
    target_label = _label(target_name)
    templates = {
        "transfer": f"【前置意图】用{source_token}给{target_token}（{target_label}）转账",
        "internal_transfer": f"【前置意图】用{source_token}向{target_token}（{target_label}）内部转账",
        "collect": f"【前置意图】用{source_token}（{source_label}）向{target_token}发起收款",
        "purchase": f"【前置意图】用{source_token}申购{target_token}（{target_label}）",
        "redeem": f"【前置意图】将{source_token}（{source_label}）赎回至{target_token}",
        "convert": f"【前置意图】将{source_token}（{source_label}）转换为{target_token}（{target_label}）",
    }
    display = {
        "transfer": f"【前置意图】转账 · {source_label} → {target_label}",
        "internal_transfer": f"【前置意图】内部转账 · {source_label} → {target_label}",
        "collect": f"【前置意图】收款 · {source_label} → {target_label}",
        "purchase": f"【前置意图】申购 · {source_label} → {target_label}",
        "redeem": f"【前置意图】赎回 · {source_label} → {target_label}",
        "convert": f"【前置意图】转换 · {source_label} → {target_label}",
    }
    return IntentPrompt(action=intent.action, prompt=templates[intent.action],
                        display=display[intent.action],
                        source_token=source_token, target_token=target_token)
