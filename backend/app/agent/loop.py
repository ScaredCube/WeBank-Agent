import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.guard import GuardProvider, GuardVerdict, build_guard_call, get_guard
from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.financial_summary import summarize_bill_comparison
from app.agent.read_completion import completed_readonly_summary
from app.agent.response_policy import tool_free_reply
from app.schemas.card_results import from_card_tool_result
from app.agent.registry import RiskLevel
from app.db.session import session_scope
from app.risk.engine import assess_tool, begin_guard_escalation, end_guard_escalation
from app.risk.injection import validate_tool_arguments
from app.tools.register import create_agent_registry
from app.tools.presentation import render_tool_result
from app.services.audit_service import TOOLS, record, record_separately
from app.services.redaction import mask_text, mask_value
from app.services.security_service import record_failure

MAX_TOOL_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5
_PREPARE_TOOLS = {
    "prepare_transfer": RiskLevel.YELLOW,
    "prepare_card_loss": RiskLevel.RED,
    "prepare_wealth_subscribe": RiskLevel.RED,
    "prepare_wealth_redeem": RiskLevel.RED,
    "prepare_cancel_subscription": RiskLevel.YELLOW,
    "prepare_internal_transfer": RiskLevel.YELLOW,
    "prepare_collection": RiskLevel.YELLOW,
    "prepare_wealth_convert": RiskLevel.RED,
}
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
logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentLoop:
    def __init__(self, llm: LLMProvider | None = None, guard: GuardProvider | None = None) -> None:
        self.llm = llm or get_llm()
        self.guard = guard if guard is not None else get_guard()

    async def stream(self, history: list[dict[str, str]], user_id: int,
                     verified_account_token: str | None = None,
                     verified_card_id: int | None = None,
                     verified_contact_token: str | None = None,
                     verified_recipient_name: str | None = None,
                     verified_transfer_amount_fen: int | None = None,
                     has_selected_contact: bool = False,
                     context_readonly_only: bool = False,
                     intent_action: str | None = None,
                     intent_tokens: tuple[str, str] | None = None,
                     intent_amount_fen: int | None = None) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        if intent_action in _INTENT_TOOLS:
            messages.insert(1, {"role": "system", "content": (
                "本轮用户消息开头包含服务端已校验的【前置意图】，其中令牌和金额均已绑定。"
                f"必须调用 {_INTENT_TOOLS[intent_action]} 处理本轮请求；"
                "不得要求用户重新选择账户、联系人，不得改用其他工具，也不得自行改写来源、目标或金额。"
            )})
        registry = create_agent_registry()
        tool_results: list[tuple[str, dict]] = []
        prior_calls: list[str] = []

        try:
            for round_index in range(MAX_TOOL_ROUNDS + 1):
                tool_calls: list[dict[str, Any]] | None = None
                content: list[str] = []
                async for chunk in self.llm.stream(messages, tools=registry.definitions()):
                    if chunk.content:
                        content.append(chunk.content)
                    if chunk.tool_calls:
                        tool_calls = chunk.tool_calls
                if not tool_calls:
                    if tool_results:
                        fully_supported = all(name in {"get_monthly_bill", "get_card_status"} and result.get("ok")
                                              for name, result in tool_results)
                        if fully_supported and len(tool_results) > 1:
                            summary = (summarize_bill_comparison(tool_results)
                                       or f"已完成 {len(tool_results)} 项查询，结果见下方。")
                        else:
                            summary = "\n\n".join(
                                ("账单已查询，明细见下方结果卡。" if name == "get_monthly_bill" and result.get("ok")
                                 else "卡片状态已查询，详见下方卡片。" if name == "get_card_status" and result.get("ok")
                                 else render_tool_result(name, result))
                                for name, result in tool_results)
                        # Keep the deterministic summary in this turn's context
                        # as well as the persisted assistant message.
                        messages.append({"role": "assistant", "content": summary})
                        yield AgentEvent("delta", {"text": summary})
                    else:
                        if getattr(self.llm, "mode", None) == "mock":
                            text = "当前是演示模式，离线 Mock 不会调用银行工具。"
                        else:
                            # Model free text is useful for greetings, explaining
                            # capabilities and asking for missing parameters.
                            # A response without an authenticated Tool result
                            # must never assert bank balances or executed actions.
                            # Scope is derived from the user's current message,
                            # never from an LLM's assertion that it used a bank Tool.
                            latest_request = next(
                                (str(item.get("content") or "") for item in reversed(history)
                                 if item.get("role") == "user"), ""
                            )
                            text = tool_free_reply(
                                "".join(content), user_request=latest_request,
                                financial_context=bool(
                                    verified_account_token or verified_card_id
                                    or verified_contact_token or has_selected_contact
                                ),
                            )
                        # The fixed reply is a real assistant turn: keep it in the
                        # local context; chat.py also persists it for later turns.
                        messages.append({"role": "assistant", "content": text})
                        yield AgentEvent("delta", {"text": text})
                    return
                if round_index == MAX_TOOL_ROUNDS or len(tool_calls) > MAX_CALLS_PER_ROUND:
                    yield AgentEvent("error", {"message": "查询步骤过多，请简化请求后重试。"})
                    return
                if any(not isinstance(call, dict) or not isinstance(call.get("id"), str)
                       or not call["id"] or call.get("type") != "function"
                       or not isinstance(call.get("function"), dict)
                       or not isinstance(call["function"].get("name"), str)
                       or not isinstance(call["function"].get("arguments"), str)
                       for call in tool_calls):
                    yield AgentEvent("error", {"message": "模型返回的工具调用格式无效。"})
                    return
                messages.append({"role": "assistant", "content": mask_text("".join(content)) or None,
                                 "tool_calls": mask_value(tool_calls)})
                for call in tool_calls:
                    function = call["function"]
                    spec = registry.get(function["name"])
                    audit_tool = spec.name if spec is not None and spec.name in TOOLS else None
                    record_separately(user_id=user_id, event_type="tool_called", tool=audit_tool, result="success")
                    rejection_reason = None
                    intent_mismatch = (
                        intent_action is not None
                        and (spec is None or spec.name != _INTENT_TOOLS.get(intent_action))
                    )
                    try:
                        args = json.loads(function["arguments"])
                        if (not isinstance(args, dict) or "session" in args or "user_id" in args
                                or mask_value(args) != args or mask_text(call["id"]) != call["id"]):
                            raise ValueError("invalid arguments")
                    except (ValueError, TypeError):
                        rejection_reason = "invalid_arguments"
                        result = {"ok": False, "data": None, "error": "查询参数无效"}
                    else:
                        argument_error = validate_tool_arguments(spec, args)
                        if argument_error is None and intent_mismatch:
                            argument_error = "模型选择的工具与前置意图不一致，请重新发起"
                            rejection_reason = "invalid_arguments"
                        if (argument_error is None and intent_action is not None
                                and intent_tokens is not None):
                            token_args = _INTENT_TOKEN_ARGS.get(intent_action)
                            if token_args is None or len(intent_tokens) != 2:
                                argument_error = "前置意图引用无效"
                                rejection_reason = "invalid_arguments"
                            elif (type(args.get("amount_fen")) is not int
                                  or intent_amount_fen is None
                                  or args["amount_fen"] != intent_amount_fen):
                                argument_error = "模型金额与用户原文不一致，已拒绝"
                                rejection_reason = "invalid_arguments"
                            else:
                                # The server, not the model, binds source and target.
                                args[token_args[0]] = intent_tokens[0]
                                args[token_args[1]] = intent_tokens[1]
                                args["amount_fen"] = intent_amount_fen
                                if intent_action == "transfer":
                                    args.pop("target_token", None)
                        # Account binding comes ONLY from the authenticated route's
                        # ownership check. The model chooses the read-only tool and month,
                        # but cannot forge, truncate or swap the selected account token.
                        # Invalid tool fields still fail the existing whitelist check.
                        if (argument_error is None and verified_account_token is not None
                                and spec is not None and spec.name == "get_monthly_bill"):
                            args["account_token"] = verified_account_token
                        if (argument_error is None and verified_account_token is not None
                                and verified_card_id is not None and spec is not None
                                and spec.name == "get_card_status"):
                            # Both fields come from the authenticated card-to-account join.
                            # Never trust an unverified model-supplied card ID or token.
                            args["account_token"] = verified_account_token
                            args["card_id"] = verified_card_id
                        if argument_error is None and spec is not None and spec.name == "prepare_transfer" and has_selected_contact:
                            if (verified_account_token is None or verified_contact_token is None
                                    or verified_recipient_name is None or verified_transfer_amount_fen is None):
                                argument_error = "请明确填写本次转账金额并核对所选账户和联系人"
                            elif (type(args.get("amount_fen")) is not int
                                    or args["amount_fen"] != verified_transfer_amount_fen):
                                argument_error = "模型金额与用户请求不一致，请核对后重新提交"
                            else:
                                # Model chooses the operation, but neither the amount
                                # nor the payer/payee identity can be silently changed.
                                args.pop("target_token", None)
                                args["source_token"] = verified_account_token
                                args["recipient_contact_token"] = verified_contact_token
                                args["recipient_name"] = verified_recipient_name
                        if (argument_error is None and context_readonly_only
                                and spec is not None and spec.name in _PREPARE_TOOLS):
                            argument_error = "请在本轮明确选择金融对象后再准备操作"
                        guard_elevated = False
                        if (argument_error is None and spec is not None and spec.handler is not None
                                and self.guard is not None):
                            try:
                                verdict = await self.guard.review(
                                    build_guard_call(spec, args, prior_calls)
                                )
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
                                    tool=audit_tool,
                                    result="failed" if failed else "denied",
                                    reason_code="guard_unavailable" if failed else "guard_rejected",
                                )
                                # A guard flag now raises the fixed-code risk one
                                # notch instead of refusing the user's request.
                                guard_elevated = True
                        if argument_error is not None:
                            result = {"ok": False, "data": None, "error": argument_error}
                            rejection_reason = "invalid_arguments"
                        elif spec is None or spec.handler is None:
                            result = {"ok": False, "data": None, "error": "工具不可用"}
                        elif _PREPARE_TOOLS.get(spec.name) == spec.risk:
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
                                yield AgentEvent("operation_result", {
                                    "kind": prepared.get("result_kind"), "data": data,
                                })
                                result = {"ok": True, "data": data, "error": None}
                            elif prepared.get("ok"):
                                prepared_action = prepared.get("action")
                                action_id = (prepared_action.get("id")
                                             if isinstance(prepared_action, dict) else None)
                                record_separately(user_id=user_id, event_type="tool_result", tool=spec.name,
                                                  action_id=action_id, transfer_id=prepared.get("transfer_id"),
                                                  result="success")
                                payload = {"action": mask_value(prepared_action)}
                                if "transfer_id" in prepared:
                                    payload["transfer_id"] = prepared["transfer_id"]
                                if "order_id" in prepared:
                                    payload["order_id"] = prepared["order_id"]
                                if "subscription_id" in prepared:
                                    payload["subscription_id"] = prepared["subscription_id"]
                                if "collection_id" in prepared:
                                    payload["collection_id"] = prepared["collection_id"]
                                if "conversion_id" in prepared:
                                    payload["conversion_id"] = prepared["conversion_id"]
                                # Never put the confirmation token into model messages or logs.
                                payload["confirmation_token"] = prepared["confirmation_token"]
                                yield AgentEvent("action_required", payload)
                                return
                            else:
                                result = {"ok": False, "data": None, "error": prepared["error"]}
                        else:
                            decision = assess_tool(spec)
                            logger.info("risk_decision tool=%s user_id=%s level=%s reasons=%s",
                                        spec.name, user_id, decision.level.value, decision.reasons)
                            if decision.level != RiskLevel.GREEN:
                                record_separately(user_id=user_id, event_type="risk_assessed", tool=audit_tool,
                                                  risk_level=decision.level.value, reasons=decision.reasons, result="denied")
                                result = {"ok": False, "data": None, "error": "操作需要进一步验证"}
                            else:
                                try:
                                    with session_scope() as session:
                                        result = await spec.handler(session=session, user_id=user_id, **args)
                                        record(session, user_id=user_id, event_type="risk_assessed", tool=audit_tool,
                                               risk_level=decision.level.value, reasons=decision.reasons, result="success")
                                        if result.get("ok"):
                                            record(session, user_id=user_id, event_type="tool_result", tool=audit_tool,
                                                   result="success")
                                        session.commit()
                                except Exception:
                                    with session_scope() as session:
                                        record(session, user_id=user_id, event_type="risk_assessed", tool=audit_tool,
                                               risk_level=decision.level.value, reasons=decision.reasons, result="success")
                                        record(session, user_id=user_id, event_type="tool_result", tool=audit_tool,
                                               result="failed", reason_code="internal_error")
                                        session.commit()
                                    raise
                    if not result.get("ok"):
                        record_separately(user_id=user_id, event_type="tool_result", tool=audit_tool,
                                          result="denied", reason_code=rejection_reason)
                    result = mask_value(result)
                    # Trusted, user-scoped data produced by the existing GREEN tool,
                    # not a chart or financial claim authored by the language model.
                    if spec is not None and spec.name == "get_monthly_bill" and result.get("ok") and isinstance(result.get("data"), dict):
                        yield AgentEvent("bill_result", {"data": result["data"]})
                    if spec is not None and spec.name == "get_card_status" and result.get("ok"):
                        safe_snapshot = from_card_tool_result(result.get("data"))
                        yield AgentEvent("card_result", {"data": safe_snapshot.model_dump()})
                    messages.append({"role": "tool", "tool_call_id": mask_text(call["id"]),
                                     "content": json.dumps(result, ensure_ascii=False)})
                    tool_results.append((function["name"], result))
                    prior_calls.append(f"{function['name']}:{'success' if result.get('ok') else 'denied'}")
                # When the requested verified read-only results are already complete,
                # the server can finish deterministically. A further model round may
                # otherwise produce redundant/unsafe tool calls without new value.
                final_readonly_text = completed_readonly_summary(history, tool_results)
                if final_readonly_text is not None:
                    yield AgentEvent("delta", {"text": final_readonly_text})
                    return
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return
