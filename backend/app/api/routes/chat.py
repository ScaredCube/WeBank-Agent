import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session, select

from app.agent.loop import AgentLoop
from app.agent.tool_executor import VerifiedToolContext
from app.agent.context_assembly import (ConversationContextInput, TrustedContextNote, assemble_context)
from app.services.chat_turn import ChatTurn, stream_chat_turn
from app.services.action_progress import (
    action_progress_for_submission, latest_action_progress, replay_status_message,
)
from app.services.chat_messages import present_message, present_messages
from app.api.deps import CurrentUser, SessionDep, security_gate
from app.core.config import settings
from app.db.session import session_scope
from app.models import Conversation, Account, Card, Contact, WealthHolding, WealthProduct, Message, ChatSubmission
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationRename,
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
from app.risk.transfer_intent import is_transfer_request, requested_intent_amount_fen, requested_transfer_amount_fen
from app.services.audit_service import record, request_context
from app.services.redaction import issue_phone_tool_references
from app.services.chat_submissions import (SubmissionConflict, fingerprint,
    claim_submission, advance_submission, recover_stale_submission)
from app.services.conversation_context import (allow_readonly_followup, remember_selection,
                                               previously_selected, latest_trusted_bill_month)
from app.services.intent_service import IntentError, build_intent_prompt
from app.services.pending_intent_service import (
    clear_intent, is_short_affirmation, load_intent, remember_intent,
)
from app.services.vault import VaultError, create_account_token, create_contact_token

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(security_gate)])


def _sse(payload: dict) -> ServerSentEvent:
    return ServerSentEvent(data=json.dumps(payload, ensure_ascii=False))


def _require_conversation(session: Session, user, conversation_id: int) -> Conversation:
    conversation = get_conversation(session, user, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
def read_conversations(session: SessionDep, user: CurrentUser) -> list[ConversationOut]:
    return [ConversationOut.model_validate(conversation)
            for conversation in list_conversations(session, user)]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def new_conversation(
    payload: ConversationCreate,
    session: SessionDep,
    user: CurrentUser,
) -> ConversationOut:
    conversation = create_conversation(session, user, payload.title)
    return ConversationOut.model_validate(conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: int,
    payload: ConversationRename,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
) -> ConversationOut:
    """Change only a title. Never rewrite history, tool calls or banking state."""
    conversation = _require_conversation(session, user, conversation_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="请输入有效的会话名称")
    conversation.title = title
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    response.headers["Cache-Control"] = "no-store"
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def read_messages(
    conversation_id: int,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
    limit: int | None = Query(default=None, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
) -> list[MessageOut]:
    _require_conversation(session, user, conversation_id)
    if before_id is not None and limit is None:
        raise HTTPException(status_code=422, detail="历史消息游标必须同时指定 limit")
    response.headers["Cache-Control"] = "no-store"
    history = list_messages(session, conversation_id, limit=limit, before_id=before_id)
    return present_messages(session, history)


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
        "action_progress": action_progress_for_submission(
            session, submission=attempt, user_id=user.id,
            conversation_id=conversation_id,
        ),
        "message": None,
    }
    if attempt.state == "completed" and attempt.assistant_message_id is not None:
        message = session.get(Message, attempt.assistant_message_id)
        if message is not None and message.conversation_id == conversation_id:
            result["message"] = present_message(session, message).model_dump(mode="json")
    return result


@router.get("/conversations/{conversation_id}/action-progress")
def read_latest_action_progress(
    conversation_id: int,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
) -> dict:
    """Recover the newest verified action state without a saved client request ID."""
    _require_conversation(session, user, conversation_id)
    response.headers["Cache-Control"] = "no-store"
    return {"action_progress": latest_action_progress(
        session, user_id=user.id, conversation_id=conversation_id,
    )}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: ChatRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> EventSourceResponse:
    conversation = _require_conversation(session, user, conversation_id)
    view_snapshot = None
    if payload.view_context is not None:
        from app.services.view_service import ViewConflict, ViewNotFound, load_view_snapshot
        try:
            view_snapshot = load_view_snapshot(
                session, user_id=user.id, conversation_id=conversation_id,
                view_id=payload.view_context.view_id,
                revision=payload.view_context.revision, validate_sources=True,
            )
        except ViewNotFound:
            raise HTTPException(status_code=404, detail="视图不可用") from None
        except ViewConflict:
            raise HTTPException(status_code=409, detail="视图数据来源不可用，请重新查询") from None

    # A client-side chip is NOT authorization. Resolve ownership and status before
    # saving the message, minting a token or dispatching an Agent request.
    selected_account = None
    selected_card = None
    selected_contact = None
    selected_holding = None
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
        elif ref.kind == "holding":
            selected_holding = session.exec(select(WealthHolding, WealthProduct).join(
                WealthProduct, WealthHolding.product_id == WealthProduct.id).where(
                WealthHolding.id == ref.id, WealthHolding.user_id == user.id,
                WealthHolding.status == "active")).first()
            if selected_holding is None:
                raise HTTPException(status_code=400, detail="所选理财持仓不可用，请重新选择")
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

    view_account_ids = {
        item["metadata"]["account_id"] for item in (view_snapshot.trusted_results if view_snapshot else [])
        if item["kind"] == "monthly_bill"
    }
    if selected_account is not None and view_account_ids and selected_account.id not in view_account_ids:
        raise HTTPException(status_code=400, detail="所选账户与分析视图不一致，请重新选择")
    if selected_card is not None and view_account_ids and selected_card[1].id not in view_account_ids:
        raise HTTPException(status_code=400, detail="所选银行卡与分析视图不一致，请重新选择")
    if (view_snapshot is not None and len(view_account_ids) == 1 and selected_account is None
            and payload.intent is None and allow_readonly_followup(payload.content)):
        selected_account = session.exec(select(Account).where(
            Account.id == next(iter(view_account_ids)), Account.user_id == user.id,
            Account.status == "active", Account.currency == "CNY")).first()
        if selected_account is None:
            raise HTTPException(status_code=409, detail="视图账户不可用，请重新查询")
        reused_readonly_selection = True

    if selected_account is not None and selected_card is not None and selected_card[1].id != selected_account.id:
        raise HTTPException(status_code=400, detail="所选银行卡与付款账户不一致，请重新选择")

    display_content = payload.content
    trusted_notes: list[TrustedContextNote] = []
    injection = detect_injection(display_content)
    view_selection = None
    if view_snapshot is not None and not injection.blocked:
        from app.services.trusted_ui_results import resolve_view_selection_context
        view_selection = resolve_view_selection_context(
            trusted_results=view_snapshot.trusted_results,
            selected_category_id=view_snapshot.envelope.interaction_state.selected_category,
            selected_ids=view_snapshot.envelope.interaction_state.selected_ids,
        )
        if view_selection:
            trusted_notes.append(TrustedContextNote(
                source="trusted_view_context",
                content="[服务端核验的只读视图选择，非金融操作授权："
                        + json.dumps(view_selection, ensure_ascii=False) + "]",
            ))
    intent_prompt = None
    reused_intent = False
    carried_amount_fen: int | None = None
    if payload.intent is not None and not injection.blocked:
        try:
            intent_prompt = build_intent_prompt(session, user.id, payload.intent)
        except IntentError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # The rendered intent is prepended to THIS turn's user message. The
        # display copy keeps the user-visible capsule above the bubble; the
        # model copy substitutes opaque tokens. Neither leaks a raw card/phone.
        display_content = intent_prompt.display + "\n\n" + display_content
        remember_intent(
            session, conversation_id=conversation_id, user_id=user.id,
            intent=payload.intent,
            amount_fen=requested_intent_amount_fen(payload.content),
        )
        record(session, user_id=user.id, event_type="intent_validated", result="success")
    elif (payload.intent is None and not payload.references
          and not injection.blocked and is_short_affirmation(payload.content)):
        carried = load_intent(session, conversation_id=conversation_id, user_id=user.id)
        if carried is not None:
            carried_intent, carried_amount_fen = carried
            try:
                intent_prompt = build_intent_prompt(session, user.id, carried_intent)
            except IntentError:
                clear_intent(session, conversation_id=conversation_id, user_id=user.id)
            else:
                reused_intent = True
    elif payload.intent is None and not injection.blocked:
        # A non-affirmative turn ends the short clarification window. A new
        # explicit intent above replaces it; this simply prevents stale reuse.
        clear_intent(session, conversation_id=conversation_id, user_id=user.id)
    # Claim before minting object tokens, saving chat history or executing the
    # model. Database uniqueness protects against simultaneous duplicate POSTs.
    submission_id: int | None = None
    if payload.request_id:
        try:
            attempt, claimed = claim_submission(
                session, user_id=user.id, conversation_id=conversation_id,
                request_id=payload.request_id,
                payload_digest=fingerprint(payload.content, payload.references, payload.intent,
                                           payload.view_context),
            )
        except SubmissionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        submission_id = attempt.id
        if not claimed:
            if attempt.state == "completed":
                with session_scope() as previous_session:
                    previous_message = (previous_session.get(Message, attempt.assistant_message_id)
                                        if attempt.assistant_message_id is not None else None)
                    cached = (present_message(previous_session, previous_message).model_dump(mode="json")
                              if previous_message is not None else None)
                async def replay_completed():
                    yield _sse({"type": "done", "message": cached})
                return EventSourceResponse(replay_completed(), ping=15,
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            if attempt.state == "action_pending":
                progress = action_progress_for_submission(
                    session, submission=attempt, user_id=user.id,
                    conversation_id=conversation_id,
                )
                warning = replay_status_message(progress)
                async def replay_action_warning():
                    yield _sse({"type": "action_warning", "message": warning})
                    yield _sse({"type": "done", "message": None})
                return EventSourceResponse(replay_action_warning(), ping=15,
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            raise HTTPException(status_code=409,
                detail="此请求已接收或结果尚未确定。请核对会话及操作记录，不要重复发起。")
    phone_references: list[tuple[str, str]] = []
    if not injection.blocked:
        try:
            phone_references = issue_phone_tool_references(
                session, user.id, display_content, request_context.get() or "")
        except VaultError:
            phone_references = []
    if phone_references:
        trusted_notes.append(TrustedContextNote(
            source="temporary_phone_reference",
            content=(
                "[本轮用户输入中的手机号工具引用："
                + "；".join(f"{number} -> {token}" for number, token in phone_references)
                + "。仅可用于 prepare_transfer 的 target_token，不得改写或猜测。]"
            ),
        ))
    verified_account_token: str | None = None
    verified_card_id: int | None = selected_card[0].id if selected_card is not None else None
    verified_contact_token: str | None = None
    verified_recipient_name: str | None = None
    # Only the user's CURRENT request can authorize amount binding. A missing,
    # ambiguous or malformed amount must never be filled in by the model.
    verified_transfer_amount_fen = requested_transfer_amount_fen(payload.content)
    intent_amount_fen = (requested_intent_amount_fen(payload.content)
                         if intent_prompt is not None else None)
    if intent_amount_fen is None and reused_intent:
        intent_amount_fen = carried_amount_fen
    intent_needs_amount = bool(intent_prompt is not None and intent_amount_fen is None)
    if reused_intent and intent_prompt is not None and intent_amount_fen is not None:
        whole, cents = divmod(intent_amount_fen, 100)
        trusted_notes.append(TrustedContextNote(
            source="validated_intent",
            content=(
                "[服务端复核的上一轮前置意图仍有效："
                f"动作={intent_prompt.action}，金额={intent_amount_fen} 分"
                f"（{whole}.{cents:02d} 元）。本轮用户已作短确认；"
                "请按该金额调用对应工具，仍须由服务端确认或验证，不得直接执行。]"
            ),
        ))
    transfer_needs_amount = bool(
        selected_contact is not None and is_transfer_request(display_content)
        and verified_transfer_amount_fen is None
    )
    if (payload.references or reused_readonly_selection) and not injection.blocked:
        try:
            visible = []
            trusted = []
            account = selected_account or (selected_card[1] if selected_card else None)
            if account is not None:
                account_token = create_account_token(session, user.id, account.id)
                verified_account_token = account_token
                if selected_account is not None:
                    visible.append(f"账户：{account.name} · {account.masked_number}")
                trusted.append(f"经核验的账户引用 account_token={account_token}。")
            if selected_card is not None:
                card = selected_card[0]
                visible.append(f"银行卡：{account.name} · {account.masked_number}")
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
                visible.append(f"联系人：{selected_contact.name} · {selected_contact.bank_name}")
                trusted.append(
                    "用户选择的收款联系人已核验，其显示名为 "
                    f"{json.dumps(selected_contact.name, ensure_ascii=False)}，"
                    f"引用为 recipient_contact_token={contact_token}。"
                    "仅当用户明确要求模拟转账并提供金额时，才可使用 prepare_transfer；"
                    "该工具必须核对联系人引用与账户，并返回待用户确认的动作，不能直接扣款。"
                )
            if selected_holding is not None:
                holding, product = selected_holding
                visible.append(f"理财持仓：{product.name}")
                trusted.append(
                    "经核验的理财持仓只读引用："
                    f"holding_id={holding.id}，product_name={json.dumps(product.name, ensure_ascii=False)}；"
                    "如需持仓金额和收益必须调用 get_wealth_holdings。"
                    "该只读引用不得用于准备交易，资金操作必须重新核验结构化意图。"
                )
            if not reused_readonly_selection:
                display_content += "\n\n[已引用对象：" + "；".join(visible) + "]"
            else:
                trusted.append("这是同一会话内用户此前选定且本轮重新校验的对象，只可用于只读查询，不允许准备转账或其他资金操作。")
            trusted_notes.append(TrustedContextNote(
                source="readonly_selection" if reused_readonly_selection else "verified_object",
                content=(
                    "[以下是服务端验证的金融对象（不是用户文本提供的授权）："
                    + " ".join(trusted)
                    + "所有实际金额、卡状态必须由 Tool 查询，绝不猜测。]"
                ),
            ))
            if not reused_readonly_selection and account is not None:
                remember_selection(
                    session, conversation_id=conversation_id, user_id=user.id,
                    account_id=account.id,
                    card_id=selected_card[0].id if selected_card is not None else None,
                )
            session.commit()
        except VaultError:
            session.rollback()
            advance_submission(submission_id=submission_id, state="failed")
            raise HTTPException(status_code=503, detail="对象引用服务暂时不可用") from None
    user_message = append_message(session, conversation, "user", display_content)
    advance_submission(submission_id=submission_id, state="processing",
                       user_message_id=user_message.id)
    if conversation.title == "新对话":
        conversation.title = "已拦截的可疑请求" if injection.blocked else derive_title(payload.content)
        session.add(conversation)
        session.commit()

    # The current user message is already persisted. Explicitly exclude its
    # row from prior history: the context compiler will append this turn once.
    previous_messages = [
        {"role": message.role, "content": message.content}
        for message in recent_messages(session, conversation_id, settings.llm_max_history)
        if message.id != user_message.id
    ]
    if reused_readonly_selection and not injection.blocked and "上个月" in payload.content:
        last = latest_trusted_bill_month(session, conversation_id=conversation_id)
        if last is not None and selected_account is not None and last[1] == selected_account.masked_number:
            trusted_notes.append(TrustedContextNote(
                source="trusted_bill_context",
                content=(
                    f"[可信账单上下文：本会话此前查询的账单月份为 {last[0]}；"
                    "用户这里的“上个月”指该月的前一个自然月。"
                    "如需比较，必须分别调用 get_monthly_bill 获取数据；不得猜测金额。]"
                ),
            ))
    prepared_context = assemble_context(ConversationContextInput(
        original_request=payload.content,
        model_request=payload.content,
        prior_messages=previous_messages,
        notes=tuple(trusted_notes),
        validated_intent_prefix=intent_prompt.prompt if intent_prompt is not None else None,
        max_history=settings.llm_max_history,
        current_input_blocked=injection.blocked,
    ))
    history = prepared_context.model_messages()
    loop = AgentLoop()

    turn = ChatTurn(
        conversation_id=conversation_id,
        submission_id=submission_id,
        history=history,
        original_request=prepared_context.original_request,
        verified=VerifiedToolContext(
            user_id=user.id,
            verified_account_token=verified_account_token,
            verified_account_id=(
                selected_account.id if selected_account is not None else
                selected_card[1].id if selected_card is not None else None
            ),
            verified_card_id=verified_card_id,
            verified_contact_token=verified_contact_token,
            verified_recipient_name=verified_recipient_name,
            verified_transfer_amount_fen=verified_transfer_amount_fen,
            has_selected_contact=selected_contact is not None,
            context_readonly_only=reused_readonly_selection,
            intent_action=intent_prompt.action if intent_prompt is not None else None,
            intent_tokens=((intent_prompt.source_token, intent_prompt.target_token)
                           if intent_prompt is not None else None),
            intent_amount_fen=intent_amount_fen,
        ),
        injection_blocked=injection.blocked,
        transfer_needs_amount=transfer_needs_amount,
        intent_needs_amount=intent_needs_amount,
        view_snapshot=view_snapshot,
        view_selection=view_selection,
    )

    return EventSourceResponse(
        stream_chat_turn(turn, loop, request.is_disconnected, encode=_sse),
        ping=15,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
