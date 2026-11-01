import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.guard import GuardProvider, GuardVerdict, build_guard_call, get_guard
from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.schemas.card_results import from_card_tool_result
from app.agent.registry import RiskLevel
from app.db.session import session_scope
from app.risk.engine import assess_tool
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
                     has_selected_contact: bool = False) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
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
                            summary = f"已完成 {len(tool_results)} 项查询，结果见下方。"
                        else:
                            summary = "\n\n".join(
                                ("账单已查询，明细见下方结果卡。" if name == "get_monthly_bill" and result.get("ok")
                                 else "卡片状态已查询，详见下方卡片。" if name == "get_card_status" and result.get("ok")
                                 else render_tool_result(name, result))
                                for name, result in tool_results)
                        yield AgentEvent("delta", {"text": summary})
                    else:
                        # Model text is untrusted: without a tool result it cannot
                        # establish any account, amount or transaction claim.
                        if getattr(self.llm, "mode", None) == "mock":
                            text = "当前是演示模式，离线 Mock 不会调用银行工具。"
                        else:
                            text = "未能通过工具完成查询或准备模拟转账。请检查请求后重试；其他银行业务暂未开放。"
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
                        guard_blocked = None
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
                                guard_blocked = "安全检查暂不可用" if failed else "操作未通过安全检查"
                                rejection_reason = "guard_unavailable" if failed else "guard_rejected"
                                if not failed:
                                    record_failure(user_id)
                        if argument_error is not None:
                            result = {"ok": False, "data": None, "error": argument_error}
                            rejection_reason = "invalid_arguments"
                        elif guard_blocked is not None:
                            result = {"ok": False, "data": None, "error": guard_blocked}
                        elif spec is None or spec.handler is None:
                            result = {"ok": False, "data": None, "error": "工具不可用"}
                        elif _PREPARE_TOOLS.get(spec.name) == spec.risk:
                            prepared = await spec.handler(user_id=user_id, **args)
                            if prepared.get("ok"):
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
                                # Never put the confirmation token into model messages or logs.
                                payload["confirmation_token"] = prepared["confirmation_token"]
                                yield AgentEvent("action_required", payload)
                                return
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
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return
