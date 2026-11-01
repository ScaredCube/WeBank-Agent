"""Bounded model/tool loop. Financial Tool execution belongs to ToolExecutor."""
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.guard import GuardProvider, get_guard
from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.financial_summary import summarize_bill_comparison
from app.agent.read_completion import completed_readonly_summary
from app.agent.response_policy import tool_free_reply
from app.agent.tool_executor import ToolExecutor, VerifiedToolContext, required_intent_tool
from app.tools.register import create_agent_registry
from app.tools.presentation import render_tool_result
from app.services.redaction import mask_text, mask_value

MAX_TOOL_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5


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
                     intent_amount_fen: int | None = None,
                     original_request: str | None = None,
                     conversation_id: int | None = None) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        if required_intent_tool(intent_action) is not None:
            messages.insert(1, {"role": "system", "content": (
                "本轮用户消息开头包含服务端已校验的【前置意图】，其中令牌和金额均已绑定。"
                f"必须调用 {required_intent_tool(intent_action)} 处理本轮请求；"
                "不得要求用户重新选择账户、联系人，不得改用其他工具，也不得自行改写来源、目标或金额。"
            )})
        registry = create_agent_registry()
        executor = ToolExecutor(registry, self.guard)
        trusted = VerifiedToolContext(
            user_id=user_id,
            conversation_id=conversation_id,
            verified_account_token=verified_account_token,
            verified_card_id=verified_card_id,
            verified_contact_token=verified_contact_token,
            verified_recipient_name=verified_recipient_name,
            verified_transfer_amount_fen=verified_transfer_amount_fen,
            has_selected_contact=has_selected_contact,
            context_readonly_only=context_readonly_only,
            intent_action=intent_action,
            intent_tokens=intent_tokens,
            intent_amount_fen=intent_amount_fen,
        )
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
                    outcome = await executor.execute(call, trusted, prior_calls)
                    for event in outcome.events:
                        yield AgentEvent(event.type, event.data)
                    if outcome.stop_reason:
                        return
                    # Approval tokens travel only in client events; all other
                    # Tool observations can safely be supplied to the model.
                    if outcome.observation is None:
                        raise RuntimeError("Nonterminal Tool execution had no observation")
                    name = call["function"]["name"]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": mask_text(call["id"]),
                        "content": json.dumps(outcome.observation, ensure_ascii=False),
                    })
                    tool_results.append((name, outcome.observation))
                    prior_calls.append(
                        f"{name}:{'success' if outcome.observation.get('ok') else 'denied'}"
                    )
                # When the requested verified read-only results are already complete,
                # the server can finish deterministically. A further model round may
                # otherwise produce redundant/unsafe tool calls without new value.
                final_readonly_text = completed_readonly_summary(
                    history, tool_results, user_request=original_request,
                )
                if final_readonly_text is not None:
                    yield AgentEvent("delta", {"text": final_readonly_text})
                    return
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return
