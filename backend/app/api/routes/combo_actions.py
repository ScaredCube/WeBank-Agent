from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, security_gate
from app.schemas.combo_actions import (
    CollectionExecuteResponse, ConversionExecuteResponse, InternalTransferExecuteResponse,
)
from app.services.collection_service import CollectionError, execute_collection
from app.services.conversion_service import ConversionError, execute_conversion
from app.services.internal_transfer_service import InternalTransferError, execute_internal_transfer

router = APIRouter(tags=["combo-actions"], dependencies=[Depends(security_gate)])


@router.post("/internal-transfers/{transfer_id}/execute",
             response_model=InternalTransferExecuteResponse)
def execute_internal(transfer_id: int, response: Response,
                     user: CurrentUser) -> InternalTransferExecuteResponse:
    try:
        result = execute_internal_transfer(user.id, transfer_id)
    except InternalTransferError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return InternalTransferExecuteResponse.model_validate(result)


@router.post("/collections/{collection_id}/execute", response_model=CollectionExecuteResponse)
def execute_collection_request(collection_id: int, response: Response,
                               user: CurrentUser) -> CollectionExecuteResponse:
    try:
        result = execute_collection(user.id, collection_id)
    except CollectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return CollectionExecuteResponse.model_validate(result)


@router.post("/wealth/conversions/{conversion_id}/execute",
             response_model=ConversionExecuteResponse)
def execute_wealth_conversion(conversion_id: int, response: Response,
                              user: CurrentUser) -> ConversionExecuteResponse:
    try:
        result = execute_conversion(user.id, conversion_id)
    except ConversionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return ConversionExecuteResponse.model_validate(result)
