import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.llm import LLMProvider, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.registry import RiskLevel
from app.db.session import session_scope
from app.tools.register import create_readonly_registry
from app.tools.presentation import render_tool_result

MAX_TOOL_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5


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
        registry = create_readonly_registry()
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
                            text = "未能通过工具完成查询。请尝试查询模拟账户余额或最近交易；其他银行业务暂未开放。"
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
                messages.append({"role": "assistant", "content": "".join(content) or None,
                                 "tool_calls": tool_calls})
                for call in tool_calls:
                    function = call["function"]
                    spec = registry.get(function["name"])
                    try:
                        args = json.loads(function["arguments"])
                        if not isinstance(args, dict) or "session" in args or "user_id" in args:
                            raise ValueError("invalid arguments")
                    except (ValueError, TypeError):
                        result = {"ok": False, "data": None, "error": "查询参数无效"}
                    else:
                        if spec is None or spec.risk != RiskLevel.GREEN or spec.handler is None:
                            result = {"ok": False, "data": None, "error": "工具不可用"}
                        else:
                            with session_scope() as session:
                                result = await spec.handler(session=session, user_id=user_id, **args)
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps(result, ensure_ascii=False)})
                    tool_results.append((function["name"], result))
        except Exception:
            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
            return
