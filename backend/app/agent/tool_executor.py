"""Authenticated Tool Call execution for the bank Agent.

The model proposes a call; this boundary validates it against the authenticated
turn, runs Guard/risk checks, invokes the existing banking handlers and records
audits. Client-only action tokens never become model observations.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.guard import GuardProvider, GuardVerdict, build_guard_call
from app.agent.registry import RiskLevel, ToolExecutionMode, ToolRegistry
from app.risk.engine import begin_guard_escalation, end_guard_escalation
from app.db.session import session_scope
from app.risk.engine import assess_tool
from app.risk.injection import validate_tool_arguments
from app.schemas.card_results import from_card_tool_result
from app.services.audit_service import TOOLS, record, record_separately
from app.services.redaction import mask_text, mask_value

# Preserve the existing risk-decision logger category for audit consumers.
logger = logging.getLogger("app.agent.loop")

# Server-validated intent is an instruction about *which* operation is authorized
# for this request. Tool arguments cannot change its source/target or amount.
_INTENT_TOOLS = {
    "transfer": "prepare_transfer",
    "internal_transfer": "prepare_internal_transfer",
    "collect": "prepare_collection",
    "purchase": "prepare_wealth_subscribe",
    "redeem": "prepare_wealth_redeem",
    "convert": "prepare_wealth_convert",
}
_INTENT_TOKEN_ARGS = {
    "transfer": ("source_token", "recipient_contact_token"),
    "internal_transfer": ("source_token", "target_token"),
    "collect": ("contact_token", "account_token"),
    "purchase": ("account_token", "product_token"),
    "redeem": ("product_token", "account_token"),
    "convert": ("source_token", "target_token"),
}


@dataclass(frozen=True)
class VerifiedToolContext:
    """Values populated by the authenticated Chat route, never model-generated."""

    user_id: int
    conversation_id: int | None = None
    verified_account_token: str | None = None
    verified_card_id: int | None = None
    verified_contact_token: str | None = None
    verified_recipient_name: str | None = None
    verified_transfer_amount_fen: int | None = None
    has_selected_contact: bool = False
    context_readonly_only: bool = False
    intent_action: str | None = None
    intent_tokens: tuple[str, str] | None = None
    intent_amount_fen: int | None = None


@dataclass(frozen=True)
class ToolClientEvent:
    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ToolExecutionOutcome:
    # None means the operation paused for an out-of-band approval. In particular,
    # no confirmation token may appear in a model-visible Tool observation.
    observation: dict[str, Any] | None
    events: tuple[ToolClientEvent, ...] = field(default_factory=tuple)
    stop_reason: str | None = None


def required_intent_tool(action: str | None) -> str | None:
    return _INTENT_TOOLS.get(action)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, guard: GuardProvider | None) -> None:
        self.registry = registry
        self.guard = guard

    async def execute(
        self, call: dict[str, Any], context: VerifiedToolContext,
        prior_calls: list[str],
    ) -> ToolExecutionOutcome:
        """Execute one already shape-validated call, preserving audit ordering."""
        function = call["function"]
        spec = self.registry.get(function["name"])
        audit_tool = spec.name if spec is not None and spec.name in TOOLS else None
        user_id = context.user_id
        record_separately(user_id=user_id, event_type="tool_called", tool=audit_tool, result="success")
        rejection_reason = None
        intent_mismatch = (
            context.intent_action is not None
            and (spec is None or spec.name != required_intent_tool(context.intent_action))
        )
        events: list[ToolClientEvent] = []
        sensitive_recipient_name = False
        try:
            args = json.loads(function["arguments"])
            if (spec is not None and spec.name == "prepare_transfer"
                    and isinstance(args, dict)
                    and isinstance(args.get("recipient_name"), str)):
                sensitive_recipient_name = mask_value(args["recipient_name"]) != args["recipient_name"]
            if (not isinstance(args, dict) or "session" in args or "user_id" in args
                    or mask_value(args) != args or mask_text(call["id"]) != call["id"]):
                raise ValueError("invalid arguments")
        except (ValueError, TypeError):
            rejection_reason = "invalid_arguments"
            result = {"ok": False, "data": None,
                      "error": ("收款人姓名不能包含手机号或其他敏感号码；请只填写姓名或称呼，"
                                "使用服务端提供的 target_token 引用传递手机号。"
                                if sensitive_recipient_name else "查询参数无效")}
        else:
            argument_error = validate_tool_arguments(spec, args)
            if argument_error is None and intent_mismatch:
                argument_error = "模型选择的工具与前置意图不一致，请重新发起"
                rejection_reason = "invalid_arguments"
            if (argument_error is None and context.intent_action is not None
                    and context.intent_tokens is not None):
                token_args = _INTENT_TOKEN_ARGS.get(context.intent_action)
                if token_args is None or len(context.intent_tokens) != 2:
                    argument_error = "前置意图引用无效"
                    rejection_reason = "invalid_arguments"
                elif (type(args.get("amount_fen")) is not int
                      or context.intent_amount_fen is None
                      or args["amount_fen"] != context.intent_amount_fen):
                    argument_error = "模型金额与用户原文不一致，已拒绝"
                    rejection_reason = "invalid_arguments"
                else:
                    args[token_args[0]] = context.intent_tokens[0]
                    args[token_args[1]] = context.intent_tokens[1]
                    args["amount_fen"] = context.intent_amount_fen
                    if context.intent_action == "transfer":
                        args.pop("target_token", None)

            # Validate scope here; inject it only at handler dispatch, after
            # the Guard sees the model-authored arguments (not private scope).
            if (argument_error is None and spec is not None
                    and spec.name == "get_latest_action_progress"
                    and context.conversation_id is None):
                argument_error = "会话范围不可用，请重新发起查询"

            # Read-only selections are rebound from server-verified objects.
            if (argument_error is None and context.verified_account_token is not None
                    and spec is not None and spec.name == "get_monthly_bill"):
                args["account_token"] = context.verified_account_token
            if (argument_error is None and context.verified_account_token is not None
                    and context.verified_card_id is not None and spec is not None
                    and spec.name == "get_card_status"):
                args["account_token"] = context.verified_account_token
                args["card_id"] = context.verified_card_id

            if (argument_error is None and spec is not None
                    and spec.name == "prepare_transfer" and context.has_selected_contact):
                if (context.verified_account_token is None or context.verified_contact_token is None
                        or context.verified_recipient_name is None
                        or context.verified_transfer_amount_fen is None):
                    argument_error = "请明确填写本次转账金额并核对所选账户和联系人"
                elif (type(args.get("amount_fen")) is not int
                      or args["amount_fen"] != context.verified_transfer_amount_fen):
                    argument_error = "模型金额与用户请求不一致，请核对后重新提交"
                else:
                    args.pop("target_token", None)
                    args["source_token"] = context.verified_account_token
                    args["recipient_contact_token"] = context.verified_contact_token
                    args["recipient_name"] = context.verified_recipient_name

            if (argument_error is None and spec is not None
                    and spec.name == "prepare_transfer"
                    and context.verified_account_token is not None):
                # The user's current explicit account selection is owned and
                # validated by Chat. Rebind it here rather than expecting the
                # model to copy an opaque token, including phone-recipient turns.
                args["source_token"] = context.verified_account_token

            if (argument_error is None and context.context_readonly_only and spec is not None
                    and spec.execution == ToolExecutionMode.PREPARE):
                argument_error = "请在本轮明确选择金融对象后再准备操作"

            guard_elevated = False
            if (argument_error is None and spec is not None and spec.handler is not None
                    and self.guard is not None):
                try:
                    verdict = await self.guard.review(build_guard_call(spec, args, prior_calls))
                except Exception:
                    verdict = GuardVerdict(False, "unavailable")
                if verdict.allowed:
                    record_separately(user_id=user_id, event_type="guard_allowed",
                                      tool=audit_tool, result="success")
                else:
                    failed = verdict.reason in {"unavailable", "invalid_response"}
                    record_separately(
                        user_id=user_id,
                        event_type="guard_failed" if failed else "guard_denied",
                        tool=audit_tool, result="failed" if failed else "denied",
                        reason_code="guard_unavailable" if failed else "guard_rejected",
                    )
                    # Mainline policy: suspicious/failed Guard review escalates
                    # trusted fixed-code risk instead of rejecting a valid call.
                    # Never relax input validation, account ownership or approval.
                    guard_elevated = True

            if argument_error is not None:
                result = {"ok": False, "data": None, "error": argument_error}
                rejection_reason = "invalid_arguments"
            elif spec is None or spec.handler is None:
                result = {"ok": False, "data": None, "error": "工具不可用"}
            elif spec.execution == ToolExecutionMode.PREPARE:
                elevation = begin_guard_escalation(guard_elevated)
                try:
                    prepared = await spec.handler(user_id=user_id, **args)
                finally:
                    end_guard_escalation(elevation)
                if prepared.get("ok") and prepared.get("executed"):
                    data = prepared.get("result") or {}
                    record_separately(
                        user_id=user_id, event_type="tool_result", tool=spec.name,
                        transfer_id=prepared.get("transfer_id"), result="success",
                    )
                    events.append(ToolClientEvent(
                        "operation_result",
                        {"kind": prepared.get("result_kind"), "data": data},
                    ))
                    result = {"ok": True, "data": data, "error": None}
                elif prepared.get("ok"):
                    prepared_action = prepared.get("action")
                    action_id = (prepared_action.get("id")
                                 if isinstance(prepared_action, dict) else None)
                    record_separately(
                        user_id=user_id, event_type="tool_result", tool=spec.name,
                        action_id=action_id, transfer_id=prepared.get("transfer_id"),
                        result="success",
                    )
                    payload = {"action": mask_value(prepared_action)}
                    for field_name in (
                        "transfer_id", "order_id", "subscription_id",
                        "collection_id", "conversion_id",
                    ):
                        if field_name in prepared:
                            payload[field_name] = prepared[field_name]
                    # Client-only, one-shot confirmation token: never an LLM observation.
                    payload["confirmation_token"] = prepared["confirmation_token"]
                    return ToolExecutionOutcome(
                        observation=None,
                        events=(ToolClientEvent("action_required", payload),),
                        stop_reason="waiting_approval",
                    )
                else:
                    result = {"ok": False, "data": None, "error": prepared["error"]}
            else:
                decision = assess_tool(spec)
                logger.info(
                    "risk_decision tool=%s user_id=%s level=%s reasons=%s",
                    spec.name, user_id, decision.level.value, decision.reasons,
                )
                if decision.level != RiskLevel.GREEN:
                    record_separately(
                        user_id=user_id, event_type="risk_assessed", tool=audit_tool,
                        risk_level=decision.level.value, reasons=decision.reasons,
                        result="denied",
                    )
                    result = {"ok": False, "data": None, "error": "操作需要进一步验证"}
                else:
                    try:
                        with session_scope() as session:
                            handler_args = (
                                {**args, "conversation_id": context.conversation_id}
                                if spec.name == "get_latest_action_progress" else args
                            )
                            result = await spec.handler(
                                session=session, user_id=user_id, **handler_args,
                            )
                            record(
                                session, user_id=user_id, event_type="risk_assessed",
                                tool=audit_tool, risk_level=decision.level.value,
                                reasons=decision.reasons, result="success",
                            )
                            if result.get("ok"):
                                record(
                                    session, user_id=user_id, event_type="tool_result",
                                    tool=audit_tool, result="success",
                                )
                            session.commit()
                    except Exception:
                        with session_scope() as session:
                            record(
                                session, user_id=user_id, event_type="risk_assessed",
                                tool=audit_tool, risk_level=decision.level.value,
                                reasons=decision.reasons, result="success",
                            )
                            record(
                                session, user_id=user_id, event_type="tool_result",
                                tool=audit_tool, result="failed", reason_code="internal_error",
                            )
                            session.commit()
                        raise

        if not result.get("ok"):
            record_separately(
                user_id=user_id, event_type="tool_result", tool=audit_tool,
                result="denied", reason_code=rejection_reason,
            )
        # Hide sensitive fields before both model observations and client read cards.
        result = mask_value(result)
        if spec is not None and spec.name == "get_monthly_bill" and result.get("ok") and isinstance(result.get("data"), dict):
            events.append(ToolClientEvent("bill_result", {"data": result["data"]}))
        if spec is not None and spec.name == "get_card_status" and result.get("ok"):
            snapshot = from_card_tool_result(result.get("data"))
            events.append(ToolClientEvent("card_result", {"data": snapshot.model_dump()}))
        return ToolExecutionOutcome(observation=result, events=tuple(events))
