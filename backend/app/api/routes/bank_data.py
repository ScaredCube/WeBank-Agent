"""Frontend-only bank data read model. Never registered as an Agent tool."""
from fastapi import APIRouter, Depends, Response, HTTPException, status

from app.api.deps import CurrentUser, SessionDep, security_gate
from app.core.config import settings
from app.models import Account
from app.services.audit_service import record
from sqlmodel import select
from pydantic import BaseModel, Field
from app.schemas.bank_data import BankAccountData, BankContactData, BankDashboardData
from app.schemas.subscriptions import SubscriptionCandidateData, SubscriptionData
from app.schemas.wealth import WealthHoldingData, WealthProductData, WealthRiskProfileData
from app.services.bank_data_service import dashboard, list_account_overview, list_contact_overview
from app.services.subscription_service import detect_candidates, list_subscriptions
from app.services.wealth_service import get_risk_profile, list_holdings, list_products

router = APIRouter(prefix="/bank", tags=["bank-data"], dependencies=[Depends(security_gate)])


@router.get("/accounts", response_model=list[BankAccountData])
def read_accounts(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[BankAccountData]:
    response.headers["Cache-Control"] = "no-store"
    return [BankAccountData.model_validate(item) for item in list_account_overview(session, user.id)]


class CreateDemoAccount(BaseModel):
    name: str = Field(min_length=2, max_length=24, pattern=r"^[一-鿿A-Za-z0-9 _-]+$")


@router.post("/accounts/demo", response_model=BankAccountData, status_code=status.HTTP_201_CREATED)
def create_demo_account(payload: CreateDemoAccount, response: Response,
                        session: SessionDep, user: CurrentUser) -> BankAccountData:
    """Opt-in synthetic account only; never an actual bank onboarding endpoint."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="模拟开户未开放")
    existing = session.exec(select(Account).where(Account.user_id == user.id)).all()
    if len(existing) >= 8:
        raise HTTPException(status_code=409, detail="模拟账户数量已达上限")
    account = Account(user_id=user.id, name=payload.name.strip(),
                      masked_number="**** 待生成", currency="CNY", balance_fen=0)
    session.add(account)
    session.flush()
    account.masked_number = f"**** {account.id:04d}"
    session.add(account)
    record(session, user_id=user.id, event_type="demo_account_created", result="success")
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return BankAccountData.model_validate(next(item for item in list_account_overview(session, user.id)
                                               if item["account_id"] == account.id))


@router.get("/contacts", response_model=list[BankContactData])
def read_contacts(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[BankContactData]:
    response.headers["Cache-Control"] = "no-store"
    return [BankContactData.model_validate(item) for item in list_contact_overview(session, user.id)]


@router.get("/dashboard", response_model=BankDashboardData)
def read_dashboard(
    response: Response, session: SessionDep, user: CurrentUser,
) -> BankDashboardData:
    response.headers["Cache-Control"] = "no-store"
    return BankDashboardData.model_validate(dashboard(session, user.id))


@router.get("/subscriptions", response_model=list[SubscriptionData])
def read_subscriptions(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[SubscriptionData]:
    response.headers["Cache-Control"] = "no-store"
    return [SubscriptionData.model_validate(item) for item in list_subscriptions(session, user.id)]


@router.get("/subscriptions/candidates", response_model=list[SubscriptionCandidateData])
def read_subscription_candidates(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[SubscriptionCandidateData]:
    response.headers["Cache-Control"] = "no-store"
    return [SubscriptionCandidateData.model_validate(item)
            for item in detect_candidates(session, user.id)]


@router.get("/wealth/products", response_model=list[WealthProductData])
def read_wealth_products(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[WealthProductData]:
    response.headers["Cache-Control"] = "no-store"
    return [WealthProductData.model_validate(item) for item in list_products(session, user.id)]


@router.get("/wealth/holdings", response_model=list[WealthHoldingData])
def read_wealth_holdings(
    response: Response, session: SessionDep, user: CurrentUser,
) -> list[WealthHoldingData]:
    response.headers["Cache-Control"] = "no-store"
    return [WealthHoldingData.model_validate(item) for item in list_holdings(session, user.id)]


@router.get("/wealth/risk-profile", response_model=WealthRiskProfileData)
def read_wealth_risk_profile(
    response: Response, session: SessionDep, user: CurrentUser,
) -> WealthRiskProfileData:
    response.headers["Cache-Control"] = "no-store"
    return WealthRiskProfileData.model_validate(get_risk_profile(session, user.id))
