import hmac

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import CurrentUser
from app.core.config import settings
from app.schemas.security import UnlockRequest, UnlockResponse
from app.services.security_service import unlock_user

router = APIRouter(prefix="/security", tags=["security"])


@router.post("/unlock", response_model=UnlockResponse)
def unlock(payload: UnlockRequest, response: Response, user: CurrentUser) -> UnlockResponse:
    response.headers["Cache-Control"] = "no-store"
    if not settings.debug:
        raise HTTPException(status_code=400, detail="模拟解锁不可用")
    if not hmac.compare_digest(payload.code, settings.security_unlock_code):
        raise HTTPException(status_code=400, detail="解锁码错误")
    unlock_user(user.id)
    return UnlockResponse(status="unlocked", message="模拟锁定已解除。")
