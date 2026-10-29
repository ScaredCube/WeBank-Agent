from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, security_gate
from app.schemas.subscriptions import CancelSubscriptionPrepared, CancelSubscriptionResult
from app.schemas.operations import PrepareOperationRequest
from app.services.subscription_service import SubscriptionError, execute_cancel, prepare_cancel

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"],
                   dependencies=[Depends(security_gate)])


@router.post("/{subscription_id}/cancel/prepare", response_model=CancelSubscriptionPrepared)
def prepare_cancel_action(
    subscription_id: int, response: Response, user: CurrentUser,
    payload: PrepareOperationRequest | None = None,
) -> CancelSubscriptionPrepared:
    try:
        result = prepare_cancel(user.id, subscription_id=subscription_id,
                                idempotency_key=payload.idempotency_key if payload else None)
    except SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return CancelSubscriptionPrepared.model_validate(result)


@router.post("/cancel/{action_id}/execute", response_model=CancelSubscriptionResult)
def execute_cancel_action(
    action_id: int, response: Response, user: CurrentUser,
) -> CancelSubscriptionResult:
    try:
        result = execute_cancel(user.id, action_id)
    except SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return CancelSubscriptionResult.model_validate(result)
