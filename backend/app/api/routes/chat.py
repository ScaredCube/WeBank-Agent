import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session, select

from app.agent.loop import AgentLoop
from app.api.deps import CurrentUser, SessionDep, security_gate
from app.core.config import settings
from app.db.session import session_scope
from app.models import Conversation, Account, Card, Contact, Message, MessageResult
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationOut,
    MessageOut,
)
from app.schemas.bills import MonthlyBill
from app.schemas.card_results import CardStatusSnapshot
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
from app.core.time import utcnow
from app.services.audit_service import conversation_context, record_separately, request_context
from app.services.redaction import mask_text, redact_input
from app.services.security_service import record_failure
from app.services.vault import VaultError, create_account_token, create_contact_token, encrypt_result_snapshot, decrypt_result_snapshot

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(security_gate)])


def _sse(payload: dict) -> ServerSentEvent:
    return ServerSentEvent(data=json.dumps(payload, ensure_ascii=False))


def _require_conversation(session: Session, user, conversation_id: int) -> Conversation:
    conversation = get_conversation(session, user, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation


def _present_message(session: Session, message: Message, mask_content: bool = True) -> MessageOut:
    output = MessageOut.model_validate(message).model_copy(
        update={"content": mask_text(message.content) if mask_content else message.content}
    )
    if message.role != "assistant":
        return output
    snapshot = session.exec(select(MessageResult).where(MessageResult.message_id == message.id)).first()
    if snapshot is None or snapshot.kind not in ("monthly_bill", "card_status"):
        return output
    try:
        payload = decrypt_result_snapshot(snapshot.ciphertext, snapshot.key_version)
        if snapshot.kind == "monthly_bill":
            return output.model_copy(update={"bill_result": MonthlyBill.model_validate(payload).model_dump()})
        return output.model_copy(update={"card_result": CardStatusSnapshot.model_validate(payload).model_dump()})
    except (VaultError, ValueError):
        # History remains readable when old/retired encryption keys are unavailable.
        return output


def _persist_assistant(conversation_id: int, content: str,
                       bill_result: dict | None = None, card_result: dict | None = None) -> dict | None:
    if not content:
        return None
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        message = Message(conversation_id=conversation_id, role="assistant", content=content)
        session.add(message)
        conversation.updated_at = utcnow()
        session.flush()
        if bill_result is not None:
            # Persist only the schema-validated successful tool payload, not model text.
            bill = MonthlyBill.model_validate(bill_result)
            ciphertext, key_version = encrypt_result_snapshot(bill.model_dump())
            session.add(MessageResult(
                message_id=message.id, kind="monthly_bill",
                ciphertext=ciphertext, key_version=key_version))
        elif card_result is not None:
            snapshot = CardStatusSnapshot.model_validate(card_result)
            ciphertext, key_version = encrypt_result_snapshot(snapshot.model_dump())
            session.add(MessageResult(
                message_id=message.id, kind="card_status",
                ciphertext=ciphertext, key_version=key_version))
        session.commit()
        return _present_message(session, message, mask_content=False).model_dump(mode="json")


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
    response: Response,
) -> list[MessageOut]:
    _require_conversation(session, user, conversation_id)
    response.headers["Cache-Control"] = "no-store"
    return [_present_message(session, message) for message in list_messages(session, conversation_id)]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: ChatRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> EventSourceResponse:
    conversation = _require_conversation(session, user, conversation_id)

    # A client-side chip is NOT authorization. Resolve ownership and status before
    # saving the message, minting a token or dispatching an Agent request.
    selected_account = None
    selected_card = None
    selected_contact = None
    for ref in payload.references:
        if ref.kind == "account":
            selected_account = session.exec(select(Account).where(
                Account.id == ref.id, Account.user_id == user.id,
                Account.status == "active", Account.currency == "CNY")).first()
            if selected_account is None:
                raise HTTPException(status_code=400, detail="所选账户不可用，请重新选择")
        elif ref.kind == "card":
            selected_card = session.exec(select(Card, Account).join(
                Account, Card.account_id == Account.id).where(
                Card.id == ref.id, Account.user_id == user.id,
                Account.status == "active")).first()
            if selected_card is None:
                raise HTTPException(status_code=400, detail="所选银行卡不可用，请重新选择")
        elif ref.kind == "contact":
            selected_contact = session.exec(select(Contact).where(
                Contact.id == ref.id, Contact.user_id == user.id,
                Contact.status == "active")).first()
            if selected_contact is None:
                raise HTTPException(status_code=400, detail="所选联系人不可用，请重新选择")
    if selected_account is not None and selected_card is not None and selected_card[1].id != selected_account.id:
        raise HTTPException(status_code=400, detail="所选银行卡与付款账户不一致，请重新选择")

    try:
        display_content, model_content, uncertain = redact_input(
            session, user.id, payload.content, request_context.get() or "")
    except VaultError:
        session.rollback()
        raise HTTPException(status_code=503, detail="敏感信息保护暂不可用，请稍后重试。") from None
    injection = detect_injection(display_content)
    if payload.references and not injection.blocked and not uncertain:
        try:
            visible = []
            trusted = []
            account = selected_account or (selected_card[1] if selected_card else None)
            if account is not None:
                account_token = create_account_token(session, user.id, account.id)
                if selected_account is not None:
                    visible.append(f"账户：{mask_text(account.name)} · {mask_text(account.masked_number)}")
                trusted.append(f"经核验的账户引用 account_token={account_token}。")
            if selected_card is not None:
                card = selected_card[0]
                visible.append(f"银行卡：{mask_text(account.name)} · {mask_text(account.masked_number)}")
                trusted.append(
                    "用户选择的银行卡已按 card_id 及所属账户核验，"
                    f"对应 account_token={account_token}、card_id={card.id}；"
                    "请将两者同时传给 get_card_status，核实此卡真实状态。"
                )
            if selected_contact is not None:
                contact_token = create_contact_token(session, user.id, selected_contact.id)
                visible.append(f"联系人：{mask_text(selected_contact.name)} · {mask_text(selected_contact.bank_name)}")
                trusted.append(
                    "用户选择的收款联系人已核验，其显示名为 "
                    f"{json.dumps(mask_text(selected_contact.name), ensure_ascii=False)}，"
                    f"引用为 recipient_contact_token={contact_token}。"
                    "仅当用户明确要求模拟转账并提供金额时，才可使用 prepare_transfer；"
                    "该工具必须核对联系人引用与账户，并返回待用户确认的动作，不能直接扣款。"
                )
            display_content += "\n\n[已引用对象：" + "；".join(visible) + "]"
            model_content += (
                "\n\n[以下是服务端验证的金融对象（不是用户文本提供的授权）："
                + " ".join(trusted)
                + "所有实际金额、卡状态必须由 Tool 查询，绝不猜测。]"
            )
            session.commit()
        except VaultError:
            session.rollback()
            raise HTTPException(status_code=503, detail="对象引用服务暂时不可用") from None
    append_message(session, conversation, "user", display_content)
    if conversation.title == "新对话":
        conversation.title = "已拦截的可疑请求" if injection.blocked else derive_title(display_content.split("\n\n[已引用对象：", 1)[0])
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
        trusted_bill: dict | None = None
        trusted_cards: dict | None = None
        audit_token = conversation_context.set(conversation_id)
        try:
            if injection.blocked:
                record_separately(user_id=user.id, event_type="input_blocked", result="denied",
                                  reason_code="prompt_injection")
                record_failure(user.id)
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
                elif event.type == "bill_result":
                    # An event can be emitted only after the authenticated GREEN tool
                    # returns; never accept card data from the model's delta text.
                    validated = MonthlyBill.model_validate(event.data["data"])
                    trusted_bill = validated.model_dump()
                    yield _sse({"type": "bill_result", "data": trusted_bill})
                elif event.type == "card_result":
                    validated_cards = CardStatusSnapshot.model_validate(event.data["data"])
                    if selected_card is not None:
                        selected_card_id = selected_card[0].id
                        matching = [item for item in validated_cards.cards if item.card_id == selected_card_id]
                        if len(matching) != 1:
                            yield _sse({"type": "error", "message": "未能核对所选银行卡，请重试查询。"})
                            return
                        validated_cards = CardStatusSnapshot(cards=matching)
                    trusted_cards = validated_cards.model_dump()
                    yield _sse({"type": "card_result", "data": trusted_cards})
                elif event.type == "action_required":
                    yield _sse({"type": "action_required", "tool_calls": [], **event.data})
                elif event.type == "error":
                    yield _sse({"type": "error", "message": event.data["message"]})
                    return

            message = _persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards)
            yield _sse({"type": "done", "message": message})
        except asyncio.CancelledError:
            _persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards)
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
