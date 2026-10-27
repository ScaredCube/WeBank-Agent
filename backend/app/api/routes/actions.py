from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.actions import (
    CancelActionResponse, ConfirmActionRequest, ConfirmActionResponse, PendingActionResponse,
)
from app.services.action_service import cancel_pending_action, confirm_pending_action, get_pending_action

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/{action_id}", response_model=PendingActionResponse)
def read_action(
    action_id: int, response: Response, session: SessionDep, user: CurrentUser,
) -> PendingActionResponse:
    action = get_pending_action(session, user_id=user.id, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="动作不存在")
    response.headers["Cache-Control"] = "no-store"
    return PendingActionResponse.model_validate(action)


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
