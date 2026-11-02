"""Optional, bounded natural-language clarification after a no-tool verdict.

Recovery is a presentation-only call, not a second bank agent. It never
receives model-authored rejected claims, user banking identifiers, history or
bank tools. The service-side no-tool verdict stays authoritative.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
import re
from typing import Any, Protocol

from app.agent.prompt_assembly import assemble_recovery_prompt
from app.agent.response_policy import (
    ReplyDecision, ReplyRoute, _ACTION_COMPLETION, _AMOUNT_CLAIM,
    _BANK_FACT, _INTERNAL, _UNVERIFIED_LOOKUP, _UNVERIFIED_ORDER,
)
from app.risk.injection import detect_injection


class RecoveryModel(Protocol):
    def stream(
        self, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Any]: ...


# Only service-authored topics are provided to the recovery model.
_TOPICS: dict[str, str] = {
    "account_query": "还没有可信银行查询结果；询问用户想核对哪个账户或银行卡",
    "operation_status": "操作状态尚未核实；询问是否需要先在操作记录中核对",
    "transfer": "没有创建待确认转账；询问付款账户、收款对象和金额",
    "card_action": "没有准备银行卡操作；询问需要处理哪张银行卡",
    "wealth_action": "没有准备理财操作；询问产品、账户及相关金额",
    "subscription_action": "没有准备取消订阅；询问需要处理哪项订阅",
    "other_action": "本轮没有执行操作；询问用户希望处理哪项业务",
}
_MAX_JSON_CHARS = 600
_MAX_QUESTION_CHARS = 90
_VALID_ROUTES = frozenset({
    ReplyRoute.QUERY_REQUIRED, ReplyRoute.VERIFY_STATUS, ReplyRoute.CLARIFY_ACTION,
})
_FORBIDDEN = re.compile(
    r"(?:密码|验证码|完整卡号|卡号全号|已查询|已查到|系统显示|"
    r"已执行|已办理|已成功|已经成功|已处理完|免验证|不必确认|"
    r"无需核对|不用确认|直接操作|立即操作|替你|为你|代你)",
    re.IGNORECASE,
)


def _valid_question(value: object) -> bool:
    if not isinstance(value, str) or not (4 <= len(value) <= _MAX_QUESTION_CHARS):
        return False
    if value != value.strip() or "\n" in value or "\r" in value:
        return False
    if not value.endswith(("？", "?")) or value.count("？") + value.count("?") != 1:
        return False
    if any(ch.isdigit() for ch in value) or any(ch in value for ch in "<>{}￥¥"):
        return False
    if _FORBIDDEN.search(value) or detect_injection(value).blocked:
        return False
    return not any(pattern.search(value) for pattern in (
        _INTERNAL, _ACTION_COMPLETION, _UNVERIFIED_ORDER,
        _UNVERIFIED_LOOKUP, _BANK_FACT, _AMOUNT_CLAIM,
    ))


async def recover_no_tool_reply(
    decision: ReplyDecision, *, model: RecoveryModel,
) -> str:
    """Generate at most one short follow-up question, or use the safe fallback.

    Call this only after the Runtime has decided it cannot safely fetch more
    trusted evidence in the current turn. QUERY_REQUIRED and VERIFY_STATUS
    must first be considered for a real Tool lookup; recovery cannot satisfy
    those goals. Any model error or malformed output returns safe_text.

    The selected status sentence always comes from the deterministic service
    policy, never from the recovery model.
    """
    if decision.route not in _VALID_ROUTES:
        return decision.safe_text
    topic = _TOPICS.get(decision.recovery_topic or "")
    if topic is None or getattr(model, "mode", None) == "mock":
        return decision.safe_text

    messages = assemble_recovery_prompt().model_messages()
    messages.append({"role": "user", "content": json.dumps(
        {"context": topic, "expected": "one short follow-up question"},
        ensure_ascii=False,
    )})
    chunks: list[str] = []
    size = 0
    try:
        # A second LLM is an optional presentation improvement: do not hold
        # the chat open indefinitely when its provider is slow.
        async with asyncio.timeout(10):
            async for chunk in model.stream(messages, tools=None):
                if getattr(chunk, "tool_calls", None):
                    return decision.safe_text
                part = getattr(chunk, "content", "") or ""
                if not isinstance(part, str):
                    return decision.safe_text
                size += len(part)
                if size > _MAX_JSON_CHARS:
                    return decision.safe_text
                chunks.append(part)
        raw = json.loads("".join(chunks))
        if not isinstance(raw, dict) or set(raw) != {"question"}:
            return decision.safe_text
        question = raw["question"]
        if not _valid_question(question):
            return decision.safe_text
    except Exception:
        # The banking verdict is already final. A failed wording attempt may
        # not reopen tools, retry transfers, or leak model exceptions.
        return decision.safe_text

    first_sentence, sep, _ = decision.safe_text.partition("。")
    if not sep:
        return decision.safe_text
    return first_sentence + "。" + question
