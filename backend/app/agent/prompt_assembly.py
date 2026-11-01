"""Stable prompt assembly for the bank agent and its independent guard.

The caller supplies *already validated* intent metadata. This module never
accepts a free-form user message as a system instruction and grants no banking
permission. Financial authorisation stays in the tool/business layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from app.agent.prompts import GUARD_SYSTEM_PROMPT, SYSTEM_PROMPT, RESPONSE_RECOVERY_PROMPT

PromptRole = Literal["agent", "guard", "recovery"]

# An allowlist, deliberately not a user-provided tool name.
_INTENT_TOOL_NAMES: dict[str, str] = {
    "transfer": "prepare_transfer",
    "internal_transfer": "prepare_internal_transfer",
    "collect": "prepare_collection",
    "purchase": "prepare_wealth_subscribe",
    "redeem": "prepare_wealth_redeem",
    "convert": "prepare_wealth_convert",
}


@dataclass(frozen=True)
class PromptAssembly:
    role: PromptRole
    contents: tuple[str, ...]
    version: str

    def model_messages(self) -> list[dict[str, str]]:
        """Return fresh mappings; stored instructions are immutable strings."""
        return [{"role": "system", "content": text} for text in self.contents]


def _assembly(role: PromptRole, messages: list[dict[str, str]]) -> PromptAssembly:
    # Hash the *effective* system instructions, including any validated intent
    # directive; do not log the content or user identifiers.
    content = "\n\x00".join(message["content"] for message in messages)
    digest = sha256(content.encode("utf-8")).hexdigest()[:16]
    return PromptAssembly(role=role, contents=tuple(message["content"] for message in messages), version=f"{role}:{digest}")


def assemble_agent_prompt(*, verified_intent_action: str | None = None) -> PromptAssembly:
    """Build exactly the system messages used by the existing bank-agent loop.

    verified_intent_action must originate from server-validated ChatIntent
    metadata. The prompt is guidance only; the ToolExecutor still enforces the
    concrete validated intent, arguments and bank transaction boundaries.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if verified_intent_action is not None:
        tool = _INTENT_TOOL_NAMES.get(verified_intent_action)
        if tool is None:
            raise ValueError("Unknown validated intent action")
        messages.append({
            "role": "system",
            "content": (
                "本轮用户消息开头包含服务端已校验的【前置意图】，其中令牌和金额均已绑定。"
                f"必须调用 {tool} 处理本轮请求；"
                "不得要求用户重新选择账户、联系人，不得改用其他工具，也不得自行改写来源、目标或金额。"
            ),
        })
    return _assembly("agent", messages)


def assemble_guard_prompt() -> PromptAssembly:
    """The guard sees a separate policy, never an agent chat transcript."""
    return _assembly("guard", [{"role": "system", "content": GUARD_SYSTEM_PROMPT}])


def assemble_recovery_prompt() -> PromptAssembly:
    """A tool-free, question-only response repair prompt."""
    return _assembly(
        "recovery", [{"role": "system", "content": RESPONSE_RECOVERY_PROMPT}],
    )
