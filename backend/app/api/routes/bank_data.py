"""Frontend-only bank data read model. Never registered as an Agent tool."""
from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, SessionDep, security_gate
from app.schemas.wealth import WealthHoldingData, WealthProductData, WealthRiskProfileData
from app.services.wealth_service import get_risk_profile, list_holdings, list_products

router = APIRouter(prefix="/bank", tags=["bank-data"], dependencies=[Depends(security_gate)])


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
