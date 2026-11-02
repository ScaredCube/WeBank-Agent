"""Tool-free reply after a fixed action dialog returns its final status."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.agent.llm import LLMProvider
from app.agent.prompt_assembly import assemble_action_reply_prompt
from app.risk.injection import detect_injection

_INTERNAL = re.compile(
    r"(?:confirmation_token|account_token|recipient_contact_token|"
    r"source_token|target_token|system_prompt|api[_ -]?key|"
    r"<[A-Z_]+_[A-Za-z0-9]+>)",
    re.IGNORECASE,
)


async def compose_action_reply(
    fact: dict[str, Any], *, model: LLMProvider, timeout: float = 8.0,
) -> str | None:
    messages = assemble_action_reply_prompt().model_messages()
    messages.append({"role": "user", "content": json.dumps(fact, ensure_ascii=False)})
    chunks: list[str] = []
    try:
        async with asyncio.timeout(timeout):
            async for chunk in model.stream(messages, tools=None):
                if getattr(chunk, "tool_calls", None):
                    return None
                part = getattr(chunk, "content", "") or ""
                if not isinstance(part, str):
                    return None
                chunks.append(part)
                if sum(len(item) for item in chunks) > 800:
                    return None
    except Exception:
        return None
    text = "".join(chunks).strip()
    if not 4 <= len(text) <= 500 or detect_injection(text).blocked or _INTERNAL.search(text):
        return None
    return text
