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
from app.models import Conversation, Account, Card, Contact, Message, MessageResult, ChatSubmission
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationOut,
    MessageOut,
)
from app.schemas.bills import MonthlyBill
from app.schemas.card_results import CardStatusSnapshot
from app.schemas.tool_results import ToolResultBundle, ToolResultItem
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
from app.risk.transfer_intent import is_transfer_request, requested_transfer_amount_fen
from app.core.time import utcnow
from app.services.audit_service import conversation_context, record_separately, request_context
from app.services.redaction import mask_text, redact_input
from app.services.security_service import record_failure
from app.services.chat_submissions import (SubmissionConflict, fingerprint,
    claim_submission, advance_submission, recover_stale_submission)
from app.services.conversation_context import (allow_readonly_followup, remember_selection,
                                               previously_selected, latest_trusted_bill_month)
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
    if snapshot is None or snapshot.kind not in ("monthly_bill", "card_status", "tool_results"):
        return output
    try:
        payload = decrypt_result_snapshot(snapshot.ciphertext, snapshot.key_version)
        if snapshot.kind == "tool_results":
            validated = ToolResultBundle.model_validate(payload)
        else:
            validated = ToolResultBundle(items=[ToolResultItem(
                kind=snapshot.kind, data=payload
            )])
        values = [item.model_dump() for item in validated.items]
        first_bill = next((item["data"] for item in values if item["kind"] == "monthly_bill"), None)
        first_card = next((item["data"] for item in values if item["kind"] == "card_status"), None)
        return output.model_copy(update={
            "tool_results": values, "bill_result": first_bill, "card_result": first_card,
        })
    except (VaultError, ValueError):
        # History remains readable when old/retired encryption keys are unavailable.
        return output


def _persist_assistant(conversation_id: int, content: str,
                       bill_result: dict | None = None, card_result: dict | None = None,
                       tool_results: list[dict] | None = None,
                       submission_id: int | None = None) -> dict | None:
    if not content and not (tool_results or bill_result or card_result):
        if submission_id is not None:
            advance_submission(submission_id=submission_id, state="completed")
        return None
    if not content:
        content = "已完成查询，结果见下方卡片。"
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        message = Message(conversation_id=conversation_id, role="assistant", content=content)
        session.add(message)
        conversation.updated_at = utcnow()
        session.flush()
        data = tool_results if tool_results is not None else (
            ([{"kind": "monthly_bill", "data": bill_result}] if bill_result is not None else [])
            + ([{"kind": "card_status", "data": card_result}] if card_result is not None else [])
        )
        if data:
            validated = ToolResultBundle.model_validate({"items": data})
            if len(validated.items) == 1:
                item = validated.items[0]
                snapshot_kind, payload = item.kind, item.data
            else:
                snapshot_kind, payload = "tool_results", validated.model_dump()
            ciphertext, key_version = encrypt_result_snapshot(payload)
            session.add(MessageResult(
                message_id=message.id, kind=snapshot_kind,
                ciphertext=ciphertext, key_version=key_version))
        if submission_id is not None:
            # Atomic success boundary: persisted response and request completion
            # must commit together, never in two separate transactions.
            submission = session.get(ChatSubmission, submission_id)
            if submission is None or submission.conversation_id != conversation_id:
                raise RuntimeError("Chat submission ownership invariant failed")
            submission.state = "completed"
            submission.assistant_message_id = message.id
            submission.updated_at = utcnow()
            session.add(submission)
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


@router.get("/conversations/{conversation_id}/requests/{request_id}")
def read_submission_status(
    conversation_id: int,
    request_id: str,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
) -> dict:
    """Safe retry inspection: never returns Tool tokens or confirmation tokens."""
    _require_conversation(session, user, conversation_id)
    response.headers["Cache-Control"] = "no-store"
    attempt = session.exec(select(ChatSubmission).where(
        ChatSubmission.user_id == user.id,
        ChatSubmission.conversation_id == conversation_id,
        ChatSubmission.request_id == request_id,
    )).first()
    if attempt is None:
        raise HTTPException(status_code=404, detail="请求不存在")
    recover_stale_submission(session, attempt)
    result: dict = {
        "request_id": attempt.request_id,
        "state": attempt.state,
        "user_message_id": attempt.user_message_id,
        "pending_action_id": attempt.pending_action_id,
        "message": None,
    }
    if attempt.state == "completed" and attempt.assistant_message_id is not None:
        message = session.get(Message, attempt.assistant_message_id)
        if message is not None and message.conversation_id == conversation_id:
            result["message"] = _present_message(session, message).model_dump(mode="json")
    return result


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
    # Cached user selection is only a READ-ONLY continuity hint, not a mandate.
    # Re-check both identity and current status; never inherit context for
    # transfers, subscriptions or other prepare/execute operations.
    reused_readonly_selection = False
    if not payload.references and allow_readonly_followup(payload.content):
        prior = previously_selected(session, conversation_id=conversation_id, user_id=user.id)
        if prior is not None:
            selected_account = session.exec(select(Account).where(
                Account.id == prior.account_id, Account.user_id == user.id,
                Account.status == "active", Account.currency == "CNY")).first()
            if selected_account is None:
                raise HTTPException(status_code=400, detail="此前所选账户不可用，请重新选择")
            if prior.card_id is not None:
                selected_card = session.exec(select(Card, Account).join(
                    Account, Card.account_id == Account.id).where(
                    Card.id == prior.card_id, Card.account_id == selected_account.id,
                    Account.user_id == user.id, Account.status == "active")).first()
                if selected_card is None:
                    raise HTTPException(status_code=400, detail="此前所选银行卡不可用，请重新选择")
            reused_readonly_selection = True

    if selected_account is not None and selected_card is not None and selected_card[1].id != selected_account.id:
        raise HTTPException(status_code=400, detail="所选银行卡与付款账户不一致，请重新选择")

    try:
        display_content, model_content, uncertain = redact_input(
            session, user.id, payload.content, request_context.get() or "")
    except VaultError:
        session.rollback()
        raise HTTPException(status_code=503, detail="敏感信息保护暂不可用，请稍后重试。") from None
    injection = detect_injection(display_content)
    # Claim before minting object tokens, saving chat history or executing the
    # model. Database uniqueness protects against simultaneous duplicate POSTs.
    submission_id: int | None = None
    if payload.request_id:
        try:
            attempt, claimed = claim_submission(
                session, user_id=user.id, conversation_id=conversation_id,
                request_id=payload.request_id,
                payload_digest=fingerprint(payload.content, payload.references),
            )
        except SubmissionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        submission_id = attempt.id
        if not claimed:
            if attempt.state == "completed":
                with session_scope() as previous_session:
                    previous_message = (previous_session.get(Message, attempt.assistant_message_id)
                                        if attempt.assistant_message_id is not None else None)
                    cached = (_present_message(previous_session, previous_message).model_dump(mode="json")
                              if previous_message is not None else None)
                async def replay_completed():
                    yield _sse({"type": "done", "message": cached})
                return EventSourceResponse(replay_completed(), ping=15,
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            if attempt.state == "action_pending":
                async def replay_action_warning():
                    yield _sse({"type": "action_warning", "message":
                        "此请求已创建待确认操作，确认令牌不会重新发送。请查看操作记录；不要重新创建。"})
                    yield _sse({"type": "done", "message": None})
                return EventSourceResponse(replay_action_warning(), ping=15,
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            raise HTTPException(status_code=409,
                detail="此请求已接收或结果尚未确定。请核对会话及操作记录，不要重复发起。")
    verified_account_token: str | None = None
    verified_card_id: int | None = selected_card[0].id if selected_card is not None else None
    verified_contact_token: str | None = None
    verified_recipient_name: str | None = None
    # Only the user's CURRENT request can authorize amount binding. A missing,
    # ambiguous or malformed amount must never be filled in by the model.
    verified_transfer_amount_fen = requested_transfer_amount_fen(display_content)
    transfer_needs_amount = bool(
        selected_contact is not None and is_transfer_request(display_content)
        and verified_transfer_amount_fen is None
    )
    if (payload.references or reused_readonly_selection) and not injection.blocked and not uncertain:
        try:
            visible = []
            trusted = []
            account = selected_account or (selected_card[1] if selected_card else None)
            if account is not None:
                account_token = create_account_token(session, user.id, account.id)
                verified_account_token = account_token
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
                if verified_transfer_amount_fen is not None and account is not None:
                    verified_contact_token = contact_token
                    verified_recipient_name = selected_contact.name
                visible.append(f"联系人：{mask_text(selected_contact.name)} · {mask_text(selected_contact.bank_name)}")
                trusted.append(
                    "用户选择的收款联系人已核验，其显示名为 "
                    f"{json.dumps(mask_text(selected_contact.name), ensure_ascii=False)}，"
                    f"引用为 recipient_contact_token={contact_token}。"
                    "仅当用户明确要求模拟转账并提供金额时，才可使用 prepare_transfer；"
                    "该工具必须核对联系人引用与账户，并返回待用户确认的动作，不能直接扣款。"
                )
            if not reused_readonly_selection:
                display_content += "\n\n[已引用对象：" + "；".join(visible) + "]"
            else:
                trusted.append("这是同一会话内用户此前选定且本轮重新校验的对象，只可用于只读查询，不允许准备转账或其他资金操作。")
            model_content += (
                "\n\n[以下是服务端验证的金融对象（不是用户文本提供的授权）："
                + " ".join(trusted)
                + "所有实际金额、卡状态必须由 Tool 查询，绝不猜测。]"
            )
            if not reused_readonly_selection and account is not None:
                remember_selection(
                    session, conversation_id=conversation_id, user_id=user.id,
                    account_id=account.id,
                    card_id=selected_card[0].id if selected_card is not None else None,
                )
            session.commit()
        except VaultError:
            session.rollback()
            raise HTTPException(status_code=503, detail="对象引用服务暂时不可用") from None
    user_message = append_message(session, conversation, "user", display_content)
    advance_submission(submission_id=submission_id, state="processing",
                       user_message_id=user_message.id)
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
    if reused_readonly_selection and not injection.blocked and "上个月" in payload.content:
        last = latest_trusted_bill_month(session, conversation_id=conversation_id)
        if last is not None and selected_account is not None and last[1] == selected_account.masked_number:
            model_content += (
                f"\n\n[可信账单上下文：本会话此前查询的账单月份为 {last[0]}；"
                "用户这里的“上个月”指该月的前一个自然月。"
                "如需比较，必须分别调用 get_monthly_bill 获取数据；不得猜测金额。]"
            )
    if history:
        history[-1]["content"] = "[已拦截的可疑输入]" if injection.blocked else model_content
    loop = AgentLoop()

    async def event_stream() -> AsyncIterator[ServerSentEvent]:
        def finish_reply(content: str, bill: dict | None = None,
                         cards: dict | None = None,
                         results: list[dict] | None = None) -> dict | None:
            return _persist_assistant(
                conversation_id, content, bill, cards, results, submission_id=submission_id
            )
        collected: list[str] = []
        trusted_bill: dict | None = None
        trusted_cards: dict | None = None
        trusted_results: list[dict] = []
        audit_token = conversation_context.set(conversation_id)
        try:
            if injection.blocked:
                record_separately(user_id=user.id, event_type="input_blocked", result="denied",
                                  reason_code="prompt_injection")
                record_failure(user.id)
                text = "检测到试图绕过安全规则的请求，已拒绝。"
                yield _sse({"type": "delta", "text": text})
                yield _sse({"type": "done", "message": finish_reply(text)})
                return
            if uncertain:
                advance_submission(submission_id=submission_id, state="completed")
                yield _sse({"type": "delta", "text": "检测到无法确认的号码，请核对后重新输入。"})
                yield _sse({"type": "done", "message": None})
                return
            if transfer_needs_amount:
                clarification = "请提供明确的一笔转账金额（例如 1 元），我会先生成待确认操作供你核对。"
                yield _sse({"type": "delta", "text": clarification})
                yield _sse({"type": "done", "message": finish_reply(clarification)})
                return
            async for event in loop.stream(
                history, user_id=user.id, verified_account_token=verified_account_token,
                verified_card_id=verified_card_id,
                verified_contact_token=verified_contact_token,
                verified_recipient_name=verified_recipient_name,
                verified_transfer_amount_fen=verified_transfer_amount_fen,
                has_selected_contact=selected_contact is not None,
                context_readonly_only=reused_readonly_selection
            ):
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
                    if len(trusted_results) >= 8:
                        advance_submission(submission_id=submission_id, state="failed")
                        yield _sse({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
                        return
                    trusted_results.append({"kind": "monthly_bill", "data": trusted_bill})
                    yield _sse({"type": "bill_result", "data": trusted_bill})
                elif event.type == "card_result":
                    validated_cards = CardStatusSnapshot.model_validate(event.data["data"])
                    if selected_card is not None:
                        selected_card_id = selected_card[0].id
                        matching = [item for item in validated_cards.cards if item.card_id == selected_card_id]
                        if len(matching) != 1:
                            advance_submission(submission_id=submission_id, state="failed")
                            yield _sse({"type": "error", "message": "未能核对所选银行卡，请重试查询。"})
                            return
                        validated_cards = CardStatusSnapshot(cards=matching)
                    trusted_cards = validated_cards.model_dump()
                    if len(trusted_results) >= 8:
                        advance_submission(submission_id=submission_id, state="failed")
                        yield _sse({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
                        return
                    trusted_results.append({"kind": "card_status", "data": trusted_cards})
                    yield _sse({"type": "card_result", "data": trusted_cards})
                elif event.type == "action_required":
                    pending = event.data.get("action") or {}
                    advance_submission(submission_id=submission_id, state="action_pending",
                                       pending_action_id=pending.get("id"))
                    yield _sse({"type": "action_required", "tool_calls": [], **event.data})
                elif event.type == "error":
                    if not trusted_results:
                        # Preserve the established explicit-error contract for
                        # requests which produced no trustworthy bank result.
                        advance_submission(submission_id=submission_id, state="failed")
                        yield _sse({"type": "error", "message": event.data["message"]})
                        return
                    # An already verified card/bill must survive later model
                    # failures and be restorable from encrypted chat history.
                    explanation = "部分查询已完成，其余步骤未成功。已完成的结果见下方卡片。"
                    collected.append(explanation)
                    yield _sse({"type": "delta", "text": explanation})
                    yield _sse({"type": "done", "message": finish_reply(
                        "".join(collected), trusted_bill, trusted_cards, trusted_results)})
                    return

            message = finish_reply("".join(collected), trusted_bill, trusted_cards, trusted_results)
            yield _sse({"type": "done", "message": message})
        except asyncio.CancelledError:
            # The request was accepted, but the connection ended before the
            # client received completion. Never execute this ID twice.
            advance_submission(submission_id=submission_id, state="interrupted")
            _persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards, trusted_results)
            raise
        except Exception:
            advance_submission(submission_id=submission_id, state="failed")
            yield _sse({"type": "error", "message": "服务出现异常，请稍后再试。"})
        finally:
            conversation_context.reset(audit_token)

    return EventSourceResponse(
        event_stream(),
        ping=15,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
