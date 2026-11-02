"""Bounded, in-turn reuse of exact successful read observations.

A cached observation is specific to one turn and only to exact canonical
arguments. This module never grants bank access; ToolExecutor authorizes the
first execution, and only successful read-only observations are reusable.
"""
from __future__ import annotations

import json

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
