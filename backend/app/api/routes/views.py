"""Authenticated read-only view lifecycle endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.deps import CurrentUser, SessionDep, security_gate
from app.schemas.generative_ui import AnyViewEnvelope, ViewInteractionRequest
from app.services.view_service import (
    InvalidViewInteraction, ViewConflict, ViewNotFound,
    apply_view_interaction, load_view_snapshot,
)

router = APIRouter(prefix="/views", tags=["views"], dependencies=[Depends(security_gate)])


@router.get("/{view_id}", response_model=AnyViewEnvelope)
def get_view(view_id: str, response: Response, session: SessionDep,
             user: CurrentUser, revision: int | None = Query(default=None, ge=1)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return load_view_snapshot(session, user_id=user.id, view_id=view_id,
                                  revision=revision).envelope
    except ViewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{view_id}/interactions", response_model=AnyViewEnvelope)
def interact(view_id: str, payload: ViewInteractionRequest, response: Response,
             user: CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    try:
        return apply_view_interaction(user_id=user.id, view_id=view_id, payload=payload)
    except ViewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ViewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except InvalidViewInteraction as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
