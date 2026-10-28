from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.actions import (
    CancelActionResponse, ConfirmActionRequest, ConfirmActionResponse, PendingActionResponse,
)
from app.schemas.verification import StartVerificationRequest, VerificationResponse, VerifyCodeRequest
from app.services.action_service import cancel_pending_action, confirm_pending_action, get_pending_action
from app.services.verification_service import VerificationError, start_verification, verify_code
from app.services.redaction import mask_value

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/{action_id}", response_model=PendingActionResponse)
def read_action(
    action_id: int, response: Response, session: SessionDep, user: CurrentUser,
) -> PendingActionResponse:
    action = get_pending_action(session, user_id=user.id, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="动作不存在")
    response.headers["Cache-Control"] = "no-store"
    return PendingActionResponse.model_validate(mask_value(action))


@router.post("/{action_id}/cancel", response_model=CancelActionResponse)
def cancel_action(action_id: int, session: SessionDep, user: CurrentUser) -> CancelActionResponse:
    if not cancel_pending_action(session, user_id=user.id, action_id=action_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="取消失败：动作无效、已处理或已过期")
    return CancelActionResponse(id=action_id)


@router.post("/{action_id}/confirm", response_model=ConfirmActionResponse)
def confirm_action(
    action_id: int, payload: ConfirmActionRequest, session: SessionDep, user: CurrentUser,
) -> ConfirmActionResponse:
    if not confirm_pending_action(session, user_id=user.id, action_id=action_id, token=payload.token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="确认失败：动作无效、已处理或已过期")
    return ConfirmActionResponse(id=action_id, status="confirmed", message="已记录确认，操作尚未执行。")


@router.post("/{action_id}/verification/start", response_model=VerificationResponse)
def start_action_verification(
    action_id: int, payload: StartVerificationRequest, response: Response, user: CurrentUser,
) -> VerificationResponse:
    try:
        start_verification(user.id, action_id, payload.token)
    except VerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return VerificationResponse(action_id=action_id, status="pending", message="模拟验证已开始，操作尚未执行。")


@router.post("/{action_id}/verification/verify", response_model=VerificationResponse)
def verify_action_code(
    action_id: int, payload: VerifyCodeRequest, response: Response, user: CurrentUser,
) -> VerificationResponse:
    try:
        success = verify_code(user.id, action_id, payload.token, payload.code)
    except VerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已锁定")
    response.headers["Cache-Control"] = "no-store"
    return VerificationResponse(action_id=action_id, status="verified", message="模拟验证通过，操作尚未执行。")
