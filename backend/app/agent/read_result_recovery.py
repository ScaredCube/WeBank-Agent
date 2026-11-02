"""Bounded reuse and verified partial-read fallback for Agent turns.

A cached observation is specific to *one turn* and only to exact canonical
arguments. This module never grants bank access; ToolExecutor authorizes the
first execution, and only successful read-only observations are reusable.
"""
from __future__ import annotations

import json
from typing import Any

from app.agent.compound_read_summary import summarize_transaction_subscription_review
from app.tools.presentation import render_tool_result

# Exclude dynamic action progress and balances, mutable subscriptions, and
# any prepare/execute tools. Only these stable-in-turn read snapshots are reused.
CACHEABLE_READ_TOOLS = frozenset({
    "get_monthly_bill", "get_card_status",
    "list_recent_transactions", "detect_subscriptions",
})


def read_cache_key(name: str, argument_json: str) -> tuple[str, str] | None:
    if name not in CACHEABLE_READ_TOOLS:
        return None
    try:
        arguments = json.loads(argument_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(arguments, dict):
        return None
    return (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")))


def verified_partial_read_reply(
    results: list[tuple[str, dict[str, Any]]], *,
    user_request: str,
) -> str | None:
    """Use only successful bank READ observations; never certify a failed goal."""
    successful = [
        (name, result) for name, result in results
        if name in CACHEABLE_READ_TOOLS
        and isinstance(result, dict) and result.get("ok") is True
    ]
    if not successful:
        return None
    compound = summarize_transaction_subscription_review(
        successful, user_request=user_request,
    )
    rendered = []
    for name, result in successful:
        try:
            text = render_tool_result(name, result)
        except (TypeError, KeyError, IndexError, ValueError):
            continue
        if text:
            rendered.append(text)
    if not rendered:
        return None
    lead = "本轮部分只读查询已完成；其余步骤未能核实，请不要据此认定全部任务完成。"
    return lead + "\n\n" + (compound + "\n\n" if compound else "") + "\n\n".join(rendered)
