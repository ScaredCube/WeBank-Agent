"""Read-only bank data for the frontend negative screen; never an Agent tool."""
from sqlmodel import Session, select

from app.core.time import utcnow
from app.models import Card, Contact
from app.services.account_service import list_accounts
from app.services.redaction import mask_text
from app.services.wealth_service import get_risk_profile, list_holdings


def list_account_overview(session: Session, user_id: int) -> list[dict]:
    result = []
    for account in list_accounts(session, user_id):
        card = session.exec(select(Card).where(Card.account_id == account.id)).first()
        card_status = card.status if card is not None else "missing"
        result.append({
            "account_id": account.id, "name": mask_text(account.name),
            "masked_number": mask_text(account.masked_number), "currency": account.currency,
            "balance_fen": account.balance_fen, "status": account.status,
            "card_status": card_status,
            "can_transfer": (account.status == "active" and account.currency == "CNY"
                             and card_status == "active"),
        })
    return result


def list_contact_overview(session: Session, user_id: int) -> list[dict]:
    contacts = session.exec(select(Contact).where(
        Contact.user_id == user_id).order_by(Contact.id)).all()
    return [{"contact_id": contact.id, "name": mask_text(contact.name),
             "bank_name": mask_text(contact.bank_name),
             "masked_phone": mask_text(contact.masked_phone), "status": contact.status,
             "can_transfer": contact.status == "active"}
            for contact in contacts]


def dashboard(session: Session, user_id: int) -> dict:
    return {"accounts": list_account_overview(session, user_id),
            "contacts": list_contact_overview(session, user_id),
            "holdings": list_holdings(session, user_id),
            "risk_profile": get_risk_profile(session, user_id),
            "generated_at": utcnow().isoformat()}
