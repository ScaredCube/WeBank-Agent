import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session

from app.agent.loop import AgentLoop
from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.db.session import session_scope
from app.models import Conversation
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationOut,
    MessageOut,
)
from app.services.chat_service import (
    append_message,
    create_conversation,
    derive_title,
    get_conversation,
    list_conversations,
    list_messages,
    recent_messages,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(payload: dict) -> ServerSentEvent:
    return ServerSentEvent(data=json.dumps(payload, ensure_ascii=False))


def _require_conversation(session: Session, user, conversation_id: int) -> Conversation:
    conversation = get_conversation(session, user, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation


def _persist_assistant(conversation_id: int, content: str) -> dict | None:
    if not content:
        return None
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        message = append_message(session, conversation, "assistant", content)
        return MessageOut.model_validate(message).model_dump(mode="json")


@router.get("/conversations", response_model=list[ConversationOut])
def read_conversations(session: SessionDep, user: CurrentUser) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(conversation)
        for conversation in list_conversations(session, user)
    ]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def new_conversation(
    payload: ConversationCreate,
    session: SessionDep,
    user: CurrentUser,
) -> ConversationOut:
    conversation = create_conversation(session, user, payload.title)
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def read_messages(
    conversation_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> list[MessageOut]:
    _require_conversation(session, user, conversation_id)
    return [MessageOut.model_validate(message) for message in list_messages(session, conversation_id)]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: ChatRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> EventSourceResponse:
    conversation = _require_conversation(session, user, conversation_id)

    append_message(session, conversation, "user", payload.content)
    if conversation.title == "新对话":
        conversation.title = derive_title(payload.content)
        session.add(conversation)
        session.commit()

    history = [
        {"role": message.role, "content": message.content}
        for message in recent_messages(session, conversation_id, settings.llm_max_history)
    ]
    loop = AgentLoop()

    async def event_stream() -> AsyncIterator[ServerSentEvent]:
        collected: list[str] = []
        try:
            async for event in loop.stream(history):
                if await request.is_disconnected():
                    break
                if event.type == "delta":
                    text = event.data["text"]
                    collected.append(text)
                    yield _sse({"type": "delta", "text": text})
                elif event.type == "action_required":
                    yield _sse({"type": "action_required", "tool_calls": event.data["tool_calls"]})
                elif event.type == "error":
                    yield _sse({"type": "error", "message": event.data["message"]})
                    break

            message = _persist_assistant(conversation_id, "".join(collected))
            yield _sse({"type": "done", "message": message})
        except asyncio.CancelledError:
            _persist_assistant(conversation_id, "".join(collected))
            raise
        except Exception:
            yield _sse({"type": "error", "message": "服务出现异常，请稍后再试。"})

    return EventSourceResponse(
        event_stream(),
        ping=15,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
