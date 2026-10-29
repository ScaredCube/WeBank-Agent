from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import CurrentUser, SessionDep, security_gate
from app.schemas.cards import CardLossPrepared, CardLossResult, CardStatus
from app.schemas.operations import PrepareOperationRequest
from app.services.audit_service import record
from app.services.card_service import CardError, execute_loss, list_cards, prepare_loss

router = APIRouter(prefix="/cards", tags=["cards"], dependencies=[Depends(security_gate)])


@router.get("", response_model=list[CardStatus])
def get_cards(response: Response, session: SessionDep, user: CurrentUser) -> list[CardStatus]:
    response.headers["Cache-Control"] = "no-store"
    cards = list_cards(session, user.id)
    record(session, user_id=user.id, event_type="tool_called", tool="get_card_status", result="success")
    record(session, user_id=user.id, event_type="risk_assessed", tool="get_card_status", risk_level="green",
           reasons=("工具基础风险等级",), result="success")
    record(session, user_id=user.id, event_type="tool_result", tool="get_card_status", result="success")
    session.commit()
    return [CardStatus.model_validate(card) for card in cards]


@router.post("/{card_id}/loss/prepare", response_model=CardLossPrepared)
def prepare(card_id: int, response: Response, user: CurrentUser,
            payload: PrepareOperationRequest | None = None) -> CardLossPrepared:
    try:
        result = prepare_loss(user.id, card_id=card_id,
                              idempotency_key=payload.idempotency_key if payload else None)
    except CardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return CardLossPrepared.model_validate(result)


@router.post("/loss/{action_id}/execute", response_model=CardLossResult)
def execute(action_id: int, response: Response, user: CurrentUser) -> CardLossResult:
    try:
        result = execute_loss(user.id, action_id)
    except CardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return CardLossResult.model_validate(result)
