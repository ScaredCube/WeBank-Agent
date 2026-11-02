"""Single chat-turn orchestration; HTTP/SSE framing remains in the API route."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from app.agent.ui_composer import get_ui_composer
from app.services.chat_submissions import advance_submission
from app.db.session import session_scope
from app.services.conversation_tasks import mark_task_completed
from app.services.security_service import record_failure

logger = logging.getLogger(__name__)
EventT = TypeVar("EventT")
_SAFE_VIEW_VALIDATION_REASONS = frozenset({
    "view root does not exist", "view contains too many elements",
    "unsupported view component", "component props do not match its catalog schema",
    "view children must be unique within a parent", "leaf components cannot contain children",
    "view child does not exist", "unsupported section title", "unsupported action link",
    "metric reference does not exist", "dataset reference does not exist",
    "dataset reference has the wrong semantic kind", "data reference is not bound to a result",
    "view nesting is too deep", "view graph contains a cycle",
    "view components may have only one parent", "view root cannot have a parent",
    "view contains unreachable elements",
})


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
    resumed_read_version: datetime | None = None
    resumed_read_month: str | None = None
    prior_bill_followup_summary: str | None = None


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
        if turn.prior_bill_followup_summary is not None and not injection_blocked:
            # Reuse the encrypted server-authored read snapshot, not the model's
            # transcript. No fresh Tool call or operation authority is implied.
            summary = turn.prior_bill_followup_summary
            yield encode({"type": "delta", "text": summary})
            yield encode({"type": "done", "message": finish_reply(summary)})
            return
        if injection_blocked:
            record_separately(user_id=user_id, event_type="input_blocked", result="denied",
                              reason_code="prompt_injection")
            record_failure(user_id)
            text = "检测到试图绕过安全规则的请求，已拒绝。"
            yield encode({"type": "delta", "text": text})
            yield encode({"type": "done", "message": finish_reply(text)})
            return
        if transfer_needs_amount or intent_needs_amount:
            clarification = "请在消息中提供一个明确金额（例如 100 元），我会按前置意图校验后继续。"
            yield encode({"type": "delta", "text": clarification})
            yield encode({"type": "done", "message": finish_reply(clarification)})
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
            **({"view_selection": turn.view_selection} if turn.view_selection else {}),
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
                yield encode({"type": "card_result", "data": trusted_cards})
            elif event.type == "action_required":
                action_pending = True
                pending = event.data.get("action") or {}
                advance_submission(submission_id=submission_id, state="action_pending",
                                   pending_action_id=pending.get("id"))
                if not collected:
                    # Keep a durable assistant row so the conversation never
                    # looks empty after a tool-only prepare round.
                    collected.append("已生成待确认操作，请在固定弹窗中核对后继续。")
                yield encode({"type": "action_required", "tool_calls": [], **event.data})
            elif event.type == "error":
                if not trusted_results:
                    # Preserve the established explicit-error contract for
                    # requests which produced no trustworthy bank result.
                    advance_submission(submission_id=submission_id, state="failed")
                    yield encode({"type": "error", "message": event.data["message"]})
                    return
                # An already verified card/bill must survive later model
                # failures and be restorable from encrypted chat history.
                explanation = "部分查询已完成，其余步骤未成功。已完成的结果见下方卡片。"
                collected.append(explanation)
                yield encode({"type": "delta", "text": explanation})
                # Preserve the verified results through the normal persistence
                # and optional view composition path below.
                break

        if ui_results and not action_pending:
            # Persist the trustworthy bank result before any model presentation work.
            saved_message = persist_assistant(conversation_id, "".join(collected), trusted_bill,
                                              trusted_cards, trusted_results,
                                              submission_id=submission_id, finalize=False)
            view = None
            if settings.generative_ui_enabled:
                try:
                    from app.services.view_service import (prepare_view_composition,
                        create_or_append_view, view_context_for_composer)
                    combined, catalog = prepare_view_composition(turn.view_snapshot, ui_results)
                    yield encode({"type": "ui_status", "status": "composing"})
                    spec = await get_ui_composer().compose(
                        question=turn.original_request, catalog=catalog,
                        context=view_context_for_composer(turn.view_snapshot))
                    if spec is not None:
                        view = create_or_append_view(user_id=user_id, conversation_id=conversation_id,
                                                     results=combined, spec=spec, context=turn.view_snapshot)
                except ValidationError as exc:
                    reasons = set()
                    for error in exc.errors(include_input=False):
                        reason = str(error.get("ctx", {}).get("error", ""))
                        reasons.add(reason if reason in _SAFE_VIEW_VALIDATION_REASONS else "schema_validation")
                    logger.warning("view composition rejected: %s", ", ".join(sorted(reasons)))
                except Exception as exc:
                    logger.warning("view composition failed: %s", type(exc).__name__)
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
            message = finish_reply("".join(collected), trusted_bill, trusted_cards,
                                   trusted_results, view=context_view)
        if message is not None and turn.resumed_read_version is not None:
            # Only an explicitly resumed, matching bill can finish the task.
            # Persisted Tool results are the authority; UI wording is not.
            verified_months = {item['data']['month'] for item in trusted_results
                if item['kind'] == 'monthly_bill' and isinstance(item.get('data'), dict)
                and isinstance(item['data'].get('month'), str)}
            expected_month = (turn.resumed_read_month or
                utcnow().astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m'))
            try:
                with session_scope() as task_session:
                    mark_task_completed(task_session, conversation_id=conversation_id,
                                        user_id=user_id, resumed_version=turn.resumed_read_version,
                                        verified_months=verified_months, expected_month=expected_month)
            except Exception:
                logger.warning("pending read task finalization failed")
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
        advance_submission(submission_id=submission_id, state="failed")
        yield encode({"type": "error", "message": "服务出现异常，请稍后再试。"})
    finally:
        conversation_context.reset(audit_token)
