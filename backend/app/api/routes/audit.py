from fastapi import APIRouter, Query, Response
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import AuditLog
from app.schemas.audit import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(response: Response, session: SessionDep, user: CurrentUser,
               limit: int = Query(default=100, ge=1, le=500),
               after_id: int = Query(default=0, ge=0)) -> list[AuditOut]:
    entries = session.exec(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.id > after_id)
                           .order_by(AuditLog.id).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    return [AuditOut.model_validate(entry) for entry in entries]
