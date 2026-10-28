from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, security_gate
from app.schemas.transfers import ExecuteTransferResponse, PrepareTransferRequest, PrepareTransferResponse
from app.services.transfer_service import TransferError, execute_transfer, prepare_transfer

router = APIRouter(prefix="/transfers", tags=["transfers"], dependencies=[Depends(security_gate)])


@router.post("/prepare", response_model=PrepareTransferResponse)
def prepare(payload: PrepareTransferRequest, response: Response, user: CurrentUser) -> PrepareTransferResponse:
    try:
        result = prepare_transfer(user.id, payload)
    except TransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return PrepareTransferResponse.model_validate(result)


@router.post("/{transfer_id}/execute", response_model=ExecuteTransferResponse)
def execute(transfer_id: int, response: Response, user: CurrentUser) -> ExecuteTransferResponse:
    try:
        result = execute_transfer(user.id, transfer_id)
    except TransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return ExecuteTransferResponse.model_validate(result)
