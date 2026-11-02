"""Conversation-scoped, read-only lookup of the latest chat-prepared bank action."""
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.services.action_progress import latest_action_progress


class LatestActionProgressArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


async def get_latest_action_progress(
    session: Session, user_id: int, *, conversation_id: int,
) -> dict:
    """The server binds conversation_id. The LLM cannot select another session."""
    progress = latest_action_progress(
        session, user_id=user_id, conversation_id=conversation_id,
    )
    return {"ok": True, "data": progress, "error": None}
