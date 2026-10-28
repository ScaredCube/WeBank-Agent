from fastapi import APIRouter, Query, Response
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import AuditLog, AuditTokenContext
from app.schemas.audit import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(response: Response, session: SessionDep, user: CurrentUser,
               limit: int = Query(default=100, ge=1, le=500),
               after_id: int = Query(default=0, ge=0)) -> list[AuditOut]:
    entries = session.exec(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.id > after_id)
                           .order_by(AuditLog.id).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    contexts = session.exec(select(AuditTokenContext).where(
        AuditTokenContext.audit_id.in_([entry.id for entry in entries]))).all() if entries else []
    by_id = {context.audit_id: context for context in contexts}
    return [AuditOut.model_validate(entry).model_copy(update={
        "reference_id": by_id[entry.id].reference_id if entry.id in by_id else None,
        "entity_kind": by_id[entry.id].entity_kind if entry.id in by_id else None,
    }) for entry in entries]
