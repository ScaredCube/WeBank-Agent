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
from app.risk.injection import detect_injection
from app.services.audit_service import conversation_context, record_separately, request_context
from app.services.redaction import mask_text, redact_input
from app.services.vault import VaultError

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
        ConversationOut.model_validate(conversation).model_copy(update={"title": mask_text(conversation.title)})
        for conversation in list_conversations(session, user)
    ]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def new_conversation(
    payload: ConversationCreate,
    session: SessionDep,
    user: CurrentUser,
) -> ConversationOut:
    conversation = create_conversation(session, user, mask_text(payload.title))
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def read_messages(
    conversation_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> list[MessageOut]:
    _require_conversation(session, user, conversation_id)
    return [MessageOut.model_validate(message).model_copy(update={"content": mask_text(message.content)})
            for message in list_messages(session, conversation_id)]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: ChatRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> EventSourceResponse:
    conversation = _require_conversation(session, user, conversation_id)

    try:
        display_content, model_content, uncertain = redact_input(
            session, user.id, payload.content, request_context.get() or "")
    except VaultError:
        session.rollback()
        raise HTTPException(status_code=503, detail="敏感信息保护暂不可用，请稍后重试。") from None
    injection = detect_injection(display_content)
    append_message(session, conversation, "user", display_content)
    if conversation.title == "新对话":
        conversation.title = "已拦截的可疑请求" if injection.blocked else derive_title(display_content)
        session.add(conversation)
        session.commit()

    history = []
    for message in recent_messages(session, conversation_id, settings.llm_max_history):
        content = mask_text(message.content)
        if detect_injection(content).blocked:
            content = "[已拦截的可疑输入]"
        history.append({"role": message.role, "content": content})
    if history:
        history[-1]["content"] = "[已拦截的可疑输入]" if injection.blocked else model_content
    loop = AgentLoop()

    async def event_stream() -> AsyncIterator[ServerSentEvent]:
        collected: list[str] = []
        audit_token = conversation_context.set(conversation_id)
        try:
            if injection.blocked:
                record_separately(user_id=user.id, event_type="input_blocked", result="denied",
                                  reason_code="prompt_injection")
                text = "检测到试图绕过安全规则的请求，已拒绝。"
                yield _sse({"type": "delta", "text": text})
                yield _sse({"type": "done", "message": _persist_assistant(conversation_id, text)})
                return
            if uncertain:
                yield _sse({"type": "delta", "text": "检测到无法确认的号码，请核对后重新输入。"})
                yield _sse({"type": "done", "message": None})
                return
            async for event in loop.stream(history, user_id=user.id):
                if await request.is_disconnected():
                    break
                if event.type == "delta":
                    text = event.data["text"]
                    collected.append(text)
                    yield _sse({"type": "delta", "text": text})
                elif event.type == "action_required":
                    yield _sse({"type": "action_required", "tool_calls": [], **event.data})
                elif event.type == "error":
                    yield _sse({"type": "error", "message": event.data["message"]})
                    return

            message = _persist_assistant(conversation_id, "".join(collected))
            yield _sse({"type": "done", "message": message})
        except asyncio.CancelledError:
            _persist_assistant(conversation_id, "".join(collected))
            raise
        except Exception:
            yield _sse({"type": "error", "message": "服务出现异常，请稍后再试。"})
        finally:
            conversation_context.reset(audit_token)

    return EventSourceResponse(
        event_stream(),
        ping=15,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
