"""Bounded model/tool loop.

The model is the only author of user-visible conversational text. Deterministic
code keeps the banking boundary: tool authorization, risk checks, trusted result
cards and protocol events. Final text is reviewed against the authenticated Tool
observations before it can be emitted.
"""
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.guard import GuardProvider, get_guard
from app.agent.goal_completion import missing_bill_goal
from app.agent.compound_read_summary import missing_read_goal_for_retry
from app.agent.llm import LLMProvider, get_llm
from app.agent.prompt_assembly import assemble_agent_prompt
from app.agent.read_result_recovery import (
    CACHEABLE_READ_TOOLS, read_cache_key,
)
from app.agent.reply_grounding import (
    ReplyGroundingError, ReplyGroundingRejected, get_reply_grounding,
)
from app.agent.tool_executor import (
    ToolExecutor, VerifiedToolContext, required_intent_tool,
)
from app.core.config import settings
from app.tools.register import create_agent_registry
from app.services.redaction import mask_text, mask_value

MAX_TOOL_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5

_MODEL_UNAVAILABLE = "模型服务暂时不可用，请稍后再试。"
_GROUNDING_REJECTED = "回复未能通过可信结果校验，请重试。"
_GENERATION_FAILED = "回复生成失败，请稍后再试。"

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class _ReplyGenerationError(RuntimeError):
    pass


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
                     conversation_id: int | None = None,
                     view_selection: dict[str, Any] | None = None,
                     turn_constraints: str | None = None) -> AsyncIterator[AgentEvent]:
        # One canonical system-prompt assembly. Intent is already verified
        # upstream; the ToolExecutor remains the authority on business actions.
        messages: list[dict[str, Any]] = assemble_agent_prompt(
            verified_intent_action=intent_action,
        ).model_messages()
        messages.extend(history)
        if turn_constraints:
            messages.append({"role": "system", "content": turn_constraints})
        if view_selection:
            messages.append({
                "role": "system",
                "content": (
                    "本轮用户正在追问服务端已核验的视图选择。"
                    "只能依据上下文中已经给出的事实回答，不得重新猜测数值。"
                ),
            })
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
        read_cache: dict[tuple[str, str], dict] = {}
        prior_calls: list[str] = []
        request = original_request or ""
        continuation_target: str | None = None
        intent_nudged = False
        attempted_nonread = False
        action_status = "none"
        malformed_rounds = 0
        no_progress_rounds = 0
        continuation_violations = 0

        try:
            for round_index in range(MAX_TOOL_ROUNDS + 1):
                tool_calls: list[dict[str, Any]] | None = None
                content: list[str] = []
                async for chunk in self.llm.stream(messages, tools=registry.definitions()):
                    if chunk.content:
                        content.append(chunk.content)
                    if chunk.tool_calls:
                        tool_calls = chunk.tool_calls
                candidate = "".join(content).strip()

                if not tool_calls:
                    required_tool = required_intent_tool(intent_action)
                    if (required_tool is not None and intent_amount_fen is not None
                            and not tool_results and not intent_nudged
                            and action_status == "none"):
                        intent_nudged = True
                        messages.append({
                            "role": "system",
                            "content": (
                                "本轮用户消息开头包含服务端已校验的前置意图和金额。"
                                f"必须调用 {required_tool} 处理；不得要求用户重新提供"
                                "账户、联系人、金额或重新描述意图。"
                                "如工具返回错误，再依据错误如实说明。"
                            ),
                        })
                        continue
                    missing_goal = (missing_read_goal_for_retry(
                        tool_results, user_request=request,
                    ) or missing_bill_goal(
                        tool_results, user_request=request,
                    ))
                    if (missing_goal is not None and continuation_target is None
                            and intent_action is None
                            and round_index < MAX_TOOL_ROUNDS - 1):
                        continuation_target = missing_goal
                        messages.append({
                            "role": "system",
                            "content": (
                                "服务端只读任务覆盖检查：当前可信结果未覆盖用户明确提出的全部查询目标。"
                                f"尚未尝试的工具为 {missing_goal}。"
                                "如有足够条件，请优先调用这个只读工具完成剩余目标。"
                                "遵守现有权限与账户范围，不得执行写操作、不得重复已成功的查询。"
                                "如无法查询或需要用户选择账户，请正常解释尚未完成的目标。"
                                "不得把疑似周期扣费直接断言成重复订阅。"
                            ),
                        })
                        continue
                    if not candidate:
                        candidate = await self._ask_with_note(
                            messages,
                            note="请直接回答用户当前的问题。若缺少可信数据，请如实说明并给出下一步。",
                            tool_results=tool_results,
                            action_status=action_status,
                            request=request,
                        )
                    else:
                        candidate = await self._finalize_reply(
                            candidate, request=request,
                            tool_results=tool_results,
                            action_status=action_status,
                        )
                    messages.append({"role": "assistant", "content": candidate})
                    yield AgentEvent("delta", {"text": candidate})
                    return

                if round_index == MAX_TOOL_ROUNDS or len(tool_calls) > MAX_CALLS_PER_ROUND:
                    messages.append({
                        "role": "assistant",
                        "content": mask_text("".join(content)) or None,
                        "tool_calls": mask_value(tool_calls),
                    })
                    for call in tool_calls:
                        if not isinstance(call, dict) or not isinstance(call.get("id"), str):
                            continue
                        messages.append({
                            "role": "tool",
                            "tool_call_id": mask_text(call["id"]),
                            "content": json.dumps({
                                "ok": False, "data": None,
                                "error": "本轮工具调用已达到上限，未执行。",
                            }, ensure_ascii=False),
                        })
                    text = await self._ask_with_note(
                        messages,
                        note=(
                            "本轮工具调用已达到上限或数量过多，不能再调用工具。"
                            "请基于已经取得的可信结果回答用户；缺失的部分如实说明。"
                        ),
                        tool_results=tool_results,
                        action_status=action_status,
                        request=request,
                    )
                    messages.append({"role": "assistant", "content": text})
                    yield AgentEvent("delta", {"text": text})
                    return

                if any(not isinstance(call, dict) or not isinstance(call.get("id"), str)
                       or not call["id"] or call.get("type") != "function"
                       or not isinstance(call.get("function"), dict)
                       or not isinstance(call["function"].get("name"), str)
                       or not isinstance(call["function"].get("arguments"), str)
                       for call in tool_calls):
                    malformed_rounds += 1
                    if malformed_rounds > 1:
                        text = await self._ask_with_note(
                            messages,
                            note="工具调用格式连续无效，不能再调用工具。请基于已有可信结果回答用户。",
                            tool_results=tool_results,
                            action_status=action_status,
                            request=request,
                        )
                        messages.append({"role": "assistant", "content": text})
                        yield AgentEvent("delta", {"text": text})
                        return
                    messages.append({
                        "role": "system",
                        "content": "上一轮工具调用格式无效。请修正参数后重试，或直接回答用户。",
                    })
                    continue

                if (continuation_target is not None and (
                        len(tool_calls) != 1
                        or tool_calls[0]["function"]["name"] != continuation_target)):
                    continuation_violations += 1
                    if continuation_violations > 1:
                        text = await self._ask_with_note(
                            messages,
                            note=(
                                "服务端只允许完成剩余只读目标，不能继续调用其他工具。"
                                "请基于已有可信结果回答用户。"
                            ),
                            tool_results=tool_results,
                            action_status=action_status,
                            request=request,
                        )
                        messages.append({"role": "assistant", "content": text})
                        yield AgentEvent("delta", {"text": text})
                        return
                    messages.append({
                        "role": "system",
                        "content": (
                            f"本轮只允许调用只读工具 {continuation_target} 完成剩余查询目标。"
                            "不要调用其他工具。"
                        ),
                    })
                    continue

                messages.append({"role": "assistant", "content": mask_text("".join(content)) or None,
                                 "tool_calls": mask_value(tool_calls)})
                executed_count = 0
                stop_requested = False
                for call_index, call in enumerate(tool_calls):
                    name = call["function"]["name"]
                    cache_key = (read_cache_key(name, call["function"]["arguments"])
                                 if not attempted_nonread else None)
                    if cache_key is not None and cache_key in read_cache:
                        # Satisfy the model tool_call_id without re-executing or
                        # duplicating SSE cards, audits or trusted result rows.
                        observation = read_cache[cache_key]
                    else:
                        if name not in CACHEABLE_READ_TOOLS:
                            attempted_nonread = True
                            # A write or dynamic Tool may change state. Never
                            # serve earlier read snapshots after it is attempted.
                            read_cache.clear()
                        try:
                            outcome = await executor.execute(call, trusted, prior_calls)
                        except Exception:
                            observation = {
                                "ok": False,
                                "data": None,
                                "error": "工具执行失败，请稍后重试或改用其他方式。",
                            }
                            messages.append({
                                "role": "tool",
                                "tool_call_id": mask_text(call["id"]),
                                "content": json.dumps(observation, ensure_ascii=False),
                            })
                            continue
                        executed_count += 1
                        for event in outcome.events:
                            yield AgentEvent(event.type, event.data)
                        if outcome.stop_reason:
                            action_status = "waiting_approval"
                            stop_requested = True
                            if outcome.observation is not None:
                                observation = outcome.observation
                            else:
                                observation = {
                                    "ok": True,
                                    "data": {"status": "awaiting_user_confirmation"},
                                    "note": "操作已准备，等待用户在固定确认界面核对。",
                                }
                            messages.append({
                                "role": "tool",
                                "tool_call_id": mask_text(call["id"]),
                                "content": json.dumps(observation, ensure_ascii=False),
                            })
                            # The model must see one tool response per call. Do
                            # not execute later calls in this batch after a
                            # confirmation boundary.
                            for remaining in tool_calls[call_index + 1:]:
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": mask_text(remaining["id"]),
                                    "content": json.dumps({
                                        "ok": False,
                                        "data": None,
                                        "error": "本轮已进入用户确认流程，此工具未执行。",
                                    }, ensure_ascii=False),
                                })
                            break
                        if outcome.observation is None:
                            raise RuntimeError("Nonterminal Tool execution had no observation")
                        observation = outcome.observation
                        tool_results.append((name, observation))
                        prior_calls.append(
                            f"{name}:{'success' if observation.get('ok') else 'denied'}"
                        )
                        if cache_key is not None and observation.get("ok") is True:
                            read_cache[cache_key] = observation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": mask_text(call["id"]),
                        "content": json.dumps(observation, ensure_ascii=False),
                    })
                if stop_requested:
                    # The fixed action dialog now owns the turn. The main Agent
                    # must stop and wait for the action result; the reply is
                    # generated later by the action-result composer.
                    return
                if executed_count == 0:
                    no_progress_rounds += 1
                    if no_progress_rounds > 1:
                        text = await self._ask_with_note(
                            messages,
                            note=(
                                "查询没有取得新的可信结果，不能继续重复调用。"
                                "请基于已有结果回答用户，并说明未完成的部分。"
                            ),
                            tool_results=tool_results,
                            action_status=action_status,
                            request=request,
                        )
                        messages.append({"role": "assistant", "content": text})
                        yield AgentEvent("delta", {"text": text})
                        return
                    messages.append({
                        "role": "system",
                        "content": "这些查询已经完成，不要重复调用相同工具和参数。请基于已有结果回答用户。",
                    })
                    continue
                # No deterministic completion here: give the model another turn
                # to use the new observations and write the final answer.
            text = await self._ask_with_note(
                messages,
                note="请基于本轮已经取得的可信结果回答用户。",
                tool_results=tool_results,
                action_status=action_status,
                request=request,
            )
            messages.append({"role": "assistant", "content": text})
            yield AgentEvent("delta", {"text": text})
        except ReplyGroundingRejected:
            yield AgentEvent("error", {"message": _GROUNDING_REJECTED})
        except ReplyGroundingError:
            yield AgentEvent("error", {"message": _GENERATION_FAILED})
        except _ReplyGenerationError:
            yield AgentEvent("error", {"message": _GENERATION_FAILED})
        except Exception:
            logger.exception("agent loop failed")
            # The provider or a Tool can fail after earlier Tools succeeded.
            # Verified cards already emitted by the executor remain visible.
            yield AgentEvent("error", {"message": _MODEL_UNAVAILABLE})

    async def _ask_with_note(
        self, messages: list[dict[str, Any]], *, note: str,
        tool_results: list[tuple[str, dict]], action_status: str,
        request: str,
    ) -> str:
        """One bounded tool-free completion used to finish a turn."""
        final_messages = [*messages, {"role": "system", "content": note}]
        chunks: list[str] = []
        try:
            async for chunk in self.llm.stream(final_messages, tools=None):
                if getattr(chunk, "tool_calls", None):
                    raise _ReplyGenerationError("final turn attempted a tool call")
                part = getattr(chunk, "content", "") or ""
                if not isinstance(part, str):
                    raise _ReplyGenerationError("final turn returned non-text")
                chunks.append(part)
        except _ReplyGenerationError:
            raise
        except Exception as exc:
            raise _ReplyGenerationError("final turn unavailable") from exc
        candidate = "".join(chunks).strip()
        if not candidate:
            raise _ReplyGenerationError("final turn was empty")
        return await self._finalize_reply(
            candidate, request=request, tool_results=tool_results,
            action_status=action_status,
        )

    async def _finalize_reply(
        self, candidate: str, *, request: str,
        tool_results: list[tuple[str, dict]], action_status: str,
    ) -> str:
        if not settings.reply_grounding_enabled:
            return candidate
        grounding = get_reply_grounding(self.llm)
        return await grounding.compose(
            candidate, user_request=request, tool_results=tool_results,
            action_status=action_status,
        )
