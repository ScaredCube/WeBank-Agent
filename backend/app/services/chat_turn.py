"""Single chat-turn orchestration; HTTP/SSE framing remains in the API route."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import ValidationError
from app.agent.loop import AgentLoop
from app.agent.tool_executor import VerifiedToolContext
from app.schemas.bills import MonthlyBill
from app.schemas.card_results import CardStatusSnapshot
from app.schemas.tool_results import InternalTransferReceipt
from app.services.audit_service import conversation_context, record_separately
from app.services.chat_messages import persist_assistant, finalize_assistant
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import session_scope
from app.services.chat_submissions import advance_submission
from app.services.pending_intent_service import clear_intent
from app.services.security_service import record_failure

logger = logging.getLogger(__name__)
EventT = TypeVar("EventT")


def _clear_pending_intent(conversation_id: int, user_id: int) -> None:
    try:
        with session_scope() as session:
            clear_intent(session, conversation_id=conversation_id, user_id=user_id)
    except Exception:
        logger.warning("clearing pending intent failed")


@dataclass(frozen=True)
class ChatTurn:
    """One request's execution inputs, created after route-level authentication."""

    conversation_id: int
    submission_id: int | None
    history: list[dict[str, str]]
    original_request: str
    verified: VerifiedToolContext
    injection_blocked: bool = False
    transfer_needs_amount: bool = False
    intent_needs_amount: bool = False
    view_snapshot: Any = None
    view_selection: dict | None = None


async def stream_chat_turn(
    turn: ChatTurn,
    loop: AgentLoop,
    is_disconnected: Callable[[], Awaitable[bool]],
    encode: Callable[[dict[str, Any]], EventT],
) -> AsyncIterator[EventT]:
    """Yield encoded frames directly so SSE cancellation reaches this run."""
    conversation_id = turn.conversation_id
    user_id = turn.verified.user_id
    submission_id = turn.submission_id
    history = turn.history
    selected_card_id = turn.verified.verified_card_id
    injection_blocked = turn.injection_blocked
    transfer_needs_amount = turn.transfer_needs_amount
    intent_needs_amount = turn.intent_needs_amount
    constraints: list[str] = []
    if transfer_needs_amount:
        constraints.append(
            "本轮用户已选择收款联系人并要求转账，但没有提供明确金额。"
            "不得调用 prepare_transfer；请用自然语言询问明确的转账金额。"
        )
    if intent_needs_amount:
        constraints.append(
            "本轮前置意图缺少明确金额。不得准备或执行资金操作；"
            "请用自然语言询问用户希望处理的明确金额。"
        )

    def finish_reply(content: str, bill: dict | None = None,
                     cards: dict | None = None,
                     results: list[dict] | None = None,
                     view=None) -> dict | None:
        return persist_assistant(
            conversation_id, content, bill, cards, results,
            submission_id=submission_id, view=view,
        )
    collected: list[str] = []
    trusted_bill: dict | None = None
    trusted_cards: dict | None = None
    trusted_results: list[dict] = []
    ui_results: list[dict] = []
    saved_message: dict | None = None
    action_pending = False
    audit_token = conversation_context.set(conversation_id)
    try:
        if injection_blocked:
            record_separately(user_id=user_id, event_type="input_blocked", result="denied",
                              reason_code="prompt_injection")
            record_failure(user_id)
            text = "检测到试图绕过安全规则的请求，已拒绝。"
            yield encode({"type": "delta", "text": text})
            yield encode({"type": "done", "message": finish_reply(text)})
            return
        async for event in loop.stream(
            history, user_id=user_id,
            verified_account_token=turn.verified.verified_account_token,
            verified_card_id=turn.verified.verified_card_id,
            verified_contact_token=turn.verified.verified_contact_token,
            verified_recipient_name=turn.verified.verified_recipient_name,
            verified_transfer_amount_fen=turn.verified.verified_transfer_amount_fen,
            has_selected_contact=turn.verified.has_selected_contact,
            context_readonly_only=turn.verified.context_readonly_only,
            intent_action=turn.verified.intent_action,
            intent_tokens=turn.verified.intent_tokens,
            intent_amount_fen=turn.verified.intent_amount_fen,
            original_request=turn.original_request,
            conversation_id=conversation_id,
            view_selection=turn.view_selection,
            turn_constraints="\n".join(constraints) or None,
        ):
            if await is_disconnected():
                # The model/tool may already have completed a side effect.
                # Never mark an undelivered SSE stream as completed or retry it.
                raise asyncio.CancelledError
            if event.type == "delta":
                text = event.data["text"]
                collected.append(text)
                yield encode({"type": "delta", "text": text})
            elif event.type == "bill_result":
                # An event can be emitted only after the authenticated GREEN tool
                # returns; never accept card data from the model's delta text.
                validated = MonthlyBill.model_validate(event.data["data"])
                trusted_bill = validated.model_dump()
                if len(trusted_results) >= 8:
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
                    return
                trusted_results.append({"kind": "monthly_bill", "data": trusted_bill})
                metadata = event.data.get("trusted_metadata")
                account_id = None
                if (type(turn.verified.verified_account_id) is int
                        and turn.verified.verified_account_id > 0):
                    # The authenticated route identity is authoritative: the
                    # executor rebinds this bill call to that account token.
                    account_id = turn.verified.verified_account_id
                elif isinstance(metadata, dict):
                    candidate_id = metadata.get("account_id")
                    if type(candidate_id) is int and candidate_id > 0:
                        account_id = candidate_id
                if type(account_id) is int and account_id > 0:
                    ui_results.append({"kind": "monthly_bill", "data": trusted_bill,
                                       "metadata": {"account_id": account_id},
                                       "result_ref": uuid4().hex, "observed_at": utcnow().isoformat()})
                yield encode({"type": "bill_result", "data": trusted_bill})
            elif event.type == "operation_result":
                if event.data.get("kind") != "internal_transfer":
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": "操作结果格式异常"})
                    return
                # Executed green internal transfers must survive refresh just
                # like trusted bill/card results. The strict receipt schema
                # excludes pending actions and all client confirmation tokens.
                receipt = InternalTransferReceipt.model_validate(event.data.get("data"))
                if len(trusted_results) >= 8:
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
                    return
                saved = receipt.model_dump()
                trusted_results.append({"kind": "internal_transfer", "data": saved})
                _clear_pending_intent(conversation_id, user_id)
                yield encode({"type": "operation_result", "kind": "internal_transfer",
                              "data": saved})
            elif event.type == "card_result":
                validated_cards = CardStatusSnapshot.model_validate(event.data["data"])
                if selected_card_id is not None:
                    matching = [item for item in validated_cards.cards if item.card_id == selected_card_id]
                    if len(matching) != 1:
                        advance_submission(submission_id=submission_id, state="failed")
                        yield encode({"type": "error", "message": "未能核对所选银行卡，请重试查询。"})
                        return
                    validated_cards = CardStatusSnapshot(cards=matching)
                trusted_cards = validated_cards.model_dump()
                if len(trusted_results) >= 8:
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
                    return
                trusted_results.append({"kind": "card_status", "data": trusted_cards})
                ui_results.append({
                    "kind": "card_status", "data": trusted_cards,
                    "metadata": {}, "result_ref": uuid4().hex,
                    "observed_at": utcnow().isoformat(),
                })
                yield encode({"type": "card_result", "data": trusted_cards})
            elif event.type == "action_required":
                action_pending = True
                pending = event.data.get("action") or {}
                advance_submission(submission_id=submission_id, state="action_pending",
                                   pending_action_id=pending.get("id"))
                _clear_pending_intent(conversation_id, user_id)
                yield encode({"type": "action_required", "tool_calls": [], **event.data})
            elif event.type == "error":
                if action_pending:
                    # The fixed dialog already holds the prepared action. A
                    # wording-review failure must not turn that action into a
                    # failed submission or show a misleading error.
                    break
                if not trusted_results:
                    # Preserve the established explicit-error contract for
                    # requests which produced no trustworthy bank result.
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": event.data["message"]})
                    return
                # Verified cards already emitted stay visible. The model did
                # not produce a safe final message, so expose only the protocol
                # error and keep the trusted results.
                yield encode({"type": "error", "message": event.data["message"]})
                break

        if ui_results and not action_pending:
            # Persist the trustworthy bank result before any model presentation work.
            saved_message = persist_assistant(conversation_id, "".join(collected), trusted_bill,
                                              trusted_cards, trusted_results,
                                              submission_id=submission_id, finalize=False)
            view = None
            if settings.generative_ui_enabled:
                try:
                    from app.services.view_generation import generate_reviewed_view
                    yield encode({"type": "ui_status", "status": "composing"})
                    view = await generate_reviewed_view(
                        user_id=user_id, conversation_id=conversation_id,
                        question=turn.original_request, results=ui_results,
                        context=turn.view_snapshot, model=loop.llm,
                    )
                except Exception as exc:
                    logger.warning("view generation failed: %s", type(exc).__name__)
            if saved_message is not None:
                try:
                    message = finalize_assistant(conversation_id, saved_message["id"],
                                                 submission_id=submission_id, view=view)
                except Exception:
                    if view is None:
                        raise
                    logger.warning("view binding failed; keeping trusted result")
                    view = None
                    message = finalize_assistant(conversation_id, saved_message["id"],
                                                 submission_id=submission_id)
                if view is None:
                    yield encode({"type": "ui_status", "status": "fallback"})
                if view is not None:
                    yield encode({"type": "ui_view", "view": view.model_dump(mode="json")})
            else:
                message = None
        else:
            if trusted_bill is not None and not ui_results:
                yield encode({"type": "ui_status", "status": "fallback",
                              "reason": "trusted_source_unavailable"})
            context_view = (
                turn.view_snapshot.envelope
                if turn.view_snapshot is not None and not trusted_results and not action_pending
                else None
            )
            if action_pending and not collected:
                # The fixed dialog owns the turn. Keep the submission in
                # action_pending; the action-result composer will create the
                # assistant reply after confirmation, cancellation or expiry.
                message = None
            else:
                message = finish_reply("".join(collected), trusted_bill, trusted_cards,
                                       trusted_results, view=context_view)
        yield encode({"type": "done", "message": message})
    except asyncio.CancelledError:
        # The request was accepted, but the connection ended before the
        # client received completion. Never execute this ID twice.
        if saved_message is not None:
            try:
                finalize_assistant(conversation_id, saved_message["id"], submission_id=submission_id)
            except Exception:
                advance_submission(submission_id=submission_id, state="interrupted")
        else:
            advance_submission(submission_id=submission_id, state="interrupted")
            persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards, trusted_results)
        raise
    except Exception:
        logger.exception("chat event stream failed")
        # Never lose an answer that was already streamed to the client. Trusted
        # snapshots may be unavailable (for example when data keys are not
        # configured), but the assistant text and submission must still commit.
        message = None
        if saved_message is not None:
            try:
                message = finalize_assistant(
                    conversation_id, saved_message["id"], submission_id=submission_id,
                )
            except Exception:
                logger.exception("finalizing streamed reply failed")
                message = saved_message
        elif collected:
            try:
                message = persist_assistant(
                    conversation_id, "".join(collected), trusted_bill,
                    trusted_cards, trusted_results, submission_id=submission_id,
                )
            except Exception:
                logger.exception("persisting streamed reply failed")
        if message is not None:
            try:
                advance_submission(submission_id=submission_id, state="completed")
            except Exception:
                logger.exception("completing recovered submission failed")
            yield encode({"type": "done", "message": message})
            return
        advance_submission(submission_id=submission_id, state="failed")
        yield encode({"type": "error", "message": "服务出现异常，请稍后再试。"})
    finally:
        conversation_context.reset(audit_token)
