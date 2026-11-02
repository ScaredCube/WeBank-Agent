"""V2 bounded, tool-free verbalisation of authenticated read results.

The original Agent owns planning and Tools. This second call never executes
bank operations and cannot replace server-rendered facts. Failure is transparent:
the original deterministic reply is still the safe fallback.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Any

from app.agent.llm import LLMProvider
from app.risk.injection import detect_injection
from app.tools.presentation import render_tool_result

# This pass is not authorised to confirm financial actions.
_ANALYSIS_CUES = ("分析", "为什么", "原因", "对比", "比较", "变化", "趋势", "异常", "值得注意", "占比")


def should_synthesize_readoutcome(user_goal: str, results: list[tuple[str, dict]]) -> bool:
    """Start V2 with actual analytical requests; simple receipts stay fast."""
    return (any(cue in user_goal for cue in _ANALYSIS_CUES)
            and bool(results)
            and all(name in _READ_ONLY and result.get("ok") is True
                    for name, result in results))


_READ_ONLY = frozenset({
    "get_account_balance", "get_monthly_bill", "get_card_status",
    "list_recent_transactions", "get_wealth_products", "get_wealth_holdings",
    "get_wealth_risk_profile", "get_subscriptions", "detect_subscriptions",
    "get_latest_action_progress",
})
_UNVERIFIED_CLAIMS = re.compile(
    r"[0-9０-９￥¥%％]|(?:元|万元|块钱|一百|一千|一万)|"
    r"(?:已|已经|成功|确认|完成).{0,8}(?:转账|扣款|付款|挂失|申购|赎回|交易|执行|到账)|"
    r"(?:余额|持仓|消费总额).{0,5}(?:为|是|达到)"
)
_SYSTEM = """你是小We的独立只读结果说明助手。你只负责解释本轮经过服务端核验的银行工具结果。
仅输出 JSON：{"narrative":"简短自然的中文说明"}，不得输出 Markdown 或其他字段。
针对用户的真实目标组织回答；有依据时说明观察和分析边界，缺乏因果证据时不得推断原因。
不要输出具体数字、金额、比例、账户号码、交易状态或已执行操作的判断；
这些事实由服务端在下一段独立展示。不能声称执行、查询或验证过额外步骤。
如果只取得了部分所需数据，说明尚不能完成全部分析。无需自我介绍。"""


@dataclass(frozen=True)
class TurnOutcome:
    """Minimum read-only outcome boundary; no model-authored authority."""

    user_goal: str
    verified_results: tuple[tuple[str, dict[str, Any]], ...]
    fallback_text: str
    missing_goals: tuple[str, ...] = ()


class ResponseSynthesizer:
    def __init__(self, model: LLMProvider, *, timeout: float = 8.0) -> None:
        self.model = model
        self.timeout = timeout

    async def compose_view(self, *, user_goal: str, verified_summary: str) -> str:
        """Verbalise a validated category selection without another bank lookup.

        The deterministic aggregate remains the only source of numerical facts.
        """
        if not verified_summary or getattr(self.model, "mode", None) == "mock":
            return verified_summary
        payload = {
            "goal": user_goal,
            "verified_result_types": ["validated_view_category"],
            "verified_facts": verified_summary,
            "constraints": "Only explain what the selected aggregate supports.",
        }
        chunks: list[str] = []
        try:
            async with asyncio.timeout(self.timeout):
                async for chunk in self.model.stream([
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ], tools=None):
                    if getattr(chunk, "tool_calls", None):
                        return verified_summary
                    part = getattr(chunk, "content", "") or ""
                    if not isinstance(part, str):
                        return verified_summary
                    chunks.append(part)
                    if sum(len(item) for item in chunks) > 1200:
                        return verified_summary
            decoded = json.loads("".join(chunks))
            if not isinstance(decoded, dict) or set(decoded) != {"narrative"}:
                return verified_summary
            narrative = decoded["narrative"]
            if (not isinstance(narrative, str) or not (6 <= len(narrative) <= 350)
                    or "\n" in narrative or _UNVERIFIED_CLAIMS.search(narrative)
                    or detect_injection(narrative).blocked):
                return verified_summary
            return narrative.strip() + "\n\n" + verified_summary
        except Exception:
            return verified_summary

    async def compose(self, outcome: TurnOutcome) -> str:
        """Use a separate model call for explanation; always retain trusted facts."""
        results = outcome.verified_results
        if (not results or getattr(self.model, "mode", None) == "mock"
                or any(name not in _READ_ONLY or result.get("ok") is not True
                       for name, result in results)):
            return outcome.fallback_text
        try:
            trusted = "\n\n".join(render_tool_result(name, result)
                                    for name, result in results)
        except (ValueError, KeyError, TypeError, IndexError):
            return outcome.fallback_text
        if not trusted:
            return outcome.fallback_text
        # Do not create a second external-model exposure of privacy-masked
        # account fields or categories. The deterministic readout remains safe.
        if "[敏感号码已隐藏]" in trusted:
            return outcome.fallback_text
        # Never include raw arbitrary transcript or internal tokens in this
        # presentation pass. Only the current goal and authenticated observations.
        payload = {
            "goal": outcome.user_goal,
            "missing_goals": list(outcome.missing_goals),
            "verified_result_types": [name for name, _ in results],
            "verified_facts": trusted[:12000],
        }
        content: list[str] = []
        try:
            async with asyncio.timeout(self.timeout):
                async for chunk in self.model.stream([
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ], tools=None):
                    if getattr(chunk, "tool_calls", None):
                        return outcome.fallback_text
                    value = getattr(chunk, "content", "") or ""
                    if not isinstance(value, str):
                        return outcome.fallback_text
                    content.append(value)
                    if sum(len(part) for part in content) > 1200:
                        return outcome.fallback_text
            decoded = json.loads("".join(content))
            if not isinstance(decoded, dict) or set(decoded) != {"narrative"}:
                return outcome.fallback_text
            narrative = decoded["narrative"]
            if (not isinstance(narrative, str) or not (6 <= len(narrative) <= 350)
                    or "\n" in narrative or _UNVERIFIED_CLAIMS.search(narrative)
                    or detect_injection(narrative).blocked):
                return outcome.fallback_text
            return narrative.strip() + "\n\n" + trusted
        except Exception:
            return outcome.fallback_text
