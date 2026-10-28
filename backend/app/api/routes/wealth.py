from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, security_gate
from app.schemas.wealth import (
    AssessWealthRiskRequest, AssessWealthRiskResponse, ExecuteWealthOrderResponse,
    PrepareWealthRedeemRequest, PrepareWealthSubscribeRequest, WealthOrderPrepared,
)
from app.services.wealth_service import (
    WealthError, assess_risk, execute_order, prepare_redeem, prepare_subscribe,
)

router = APIRouter(prefix="/wealth", tags=["wealth"], dependencies=[Depends(security_gate)])


@router.post("/risk/assess", response_model=AssessWealthRiskResponse)
def assess_wealth_risk(
    payload: AssessWealthRiskRequest, response: Response, user: CurrentUser,
) -> AssessWealthRiskResponse:
    try:
        result = assess_risk(user.id, payload.answers)
    except WealthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return AssessWealthRiskResponse.model_validate(result)


@router.post("/subscribe/prepare", response_model=WealthOrderPrepared)
def prepare_subscribe_order(
    payload: PrepareWealthSubscribeRequest, response: Response, user: CurrentUser,
) -> WealthOrderPrepared:
    try:
        result = prepare_subscribe(user.id, payload)
    except WealthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return WealthOrderPrepared.model_validate(result)


@router.post("/redeem/prepare", response_model=WealthOrderPrepared)
def prepare_redeem_order(
    payload: PrepareWealthRedeemRequest, response: Response, user: CurrentUser,
) -> WealthOrderPrepared:
    try:
        result = prepare_redeem(user.id, payload)
    except WealthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return WealthOrderPrepared.model_validate(result)


@router.post("/orders/{order_id}/execute", response_model=ExecuteWealthOrderResponse)
def execute_wealth_order(
    order_id: int, response: Response, user: CurrentUser,
) -> ExecuteWealthOrderResponse:
    try:
        result = execute_order(user.id, order_id)
    except WealthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return ExecuteWealthOrderResponse.model_validate(result)
