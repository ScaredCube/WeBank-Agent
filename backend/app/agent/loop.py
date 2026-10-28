import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.registry import RiskLevel
from app.db.session import session_scope
from app.risk.engine import assess_tool
from app.tools.register import create_agent_registry
from app.tools.presentation import render_tool_result
from app.services.audit_service import TOOLS, record, record_separately
from app.services.redaction import mask_text, mask_value

MAX_TOOL_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5
logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentLoop:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm()

    async def stream(self, history: list[dict[str, str]], user_id: int) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        registry = create_agent_registry()
        tool_results: list[tuple[str, dict]] = []

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
                        yield AgentEvent("delta", {"text": "\n\n".join(
                            render_tool_result(name, result) for name, result in tool_results
                        )})
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
                    try:
                        args = json.loads(function["arguments"])
                        if (not isinstance(args, dict) or "session" in args or "user_id" in args
                                or mask_value(args) != args or mask_text(call["id"]) != call["id"]):
                            raise ValueError("invalid arguments")
                    except (ValueError, TypeError):
                        result = {"ok": False, "data": None, "error": "查询参数无效"}
                    else:
                        if spec is None or spec.handler is None:
                            result = {"ok": False, "data": None, "error": "工具不可用"}
                        elif ((spec.name == "prepare_transfer" and spec.risk == RiskLevel.YELLOW)
                              or (spec.name == "prepare_card_loss" and spec.risk == RiskLevel.RED)):
                            prepared = await spec.handler(user_id=user_id, **args)
                            if prepared.get("ok"):
                                record_separately(user_id=user_id, event_type="tool_result", tool=spec.name,
                                                  transfer_id=prepared.get("transfer_id"), result="success")
                                # Never put the confirmation token into model messages or logs.
                                yield AgentEvent("action_required", {
                                    "action": mask_value(prepared["action"]),
                                    **({"transfer_id": prepared["transfer_id"]} if "transfer_id" in prepared else {}),
                                    "confirmation_token": prepared["confirmation_token"],
                                })
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
                        record_separately(user_id=user_id, event_type="tool_result", tool=audit_tool, result="denied")
                    result = mask_value(result)
                    messages.append({"role": "tool", "tool_call_id": mask_text(call["id"]),
                                     "content": json.dumps(result, ensure_ascii=False)})
                    tool_results.append((function["name"], result))
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return
