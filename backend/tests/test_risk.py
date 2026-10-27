from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agent.registry import RiskLevel, ToolSpec
from app.core.config import Settings
from app.risk.engine import assess_tool


def tool(name: str, level: RiskLevel) -> ToolSpec:
    return ToolSpec(name=name, description="测试", parameters={}, risk=level)


DAY = datetime(2026, 10, 27, 4, tzinfo=timezone.utc)  # 12:00 China time
NIGHT = datetime(2026, 10, 26, 17, tzinfo=timezone.utc)  # 01:00 China time


def test_green_queries_stay_green_at_night():
    assert assess_tool(tool("get_account_balance", RiskLevel.GREEN), now=NIGHT).level == RiskLevel.GREEN


@pytest.mark.parametrize(("amount", "total", "expected"), [
    (100_000, 0, RiskLevel.YELLOW),
    (1, 99_999, RiskLevel.YELLOW),
    (1, 100_000, RiskLevel.RED),
    (100_001, 0, RiskLevel.RED),
])
def test_transfer_daily_limit(amount, total, expected):
    assert assess_tool(tool("transfer", RiskLevel.GREEN), now=DAY,
                       amount_fen=amount, daily_total_fen=total).level == expected


def test_night_upgrades_yellow_and_never_downgrades_red():
    assert assess_tool(tool("transfer", RiskLevel.YELLOW), now=NIGHT,
                       amount_fen=1, daily_total_fen=0).level == RiskLevel.RED
    assert assess_tool(tool("other", RiskLevel.RED), now=DAY).level == RiskLevel.RED


@pytest.mark.parametrize(("amount", "total"), [(0, 0), (-1, 0), (True, 0), (1, -1), (1, None)])
def test_invalid_transfer_context_is_rejected(amount, total):
    with pytest.raises(ValueError):
        assess_tool(tool("transfer", RiskLevel.YELLOW), now=DAY,
                    amount_fen=amount, daily_total_fen=total)


def test_timezone_and_configured_night_boundaries():
    with pytest.raises(ValueError):
        assess_tool(tool("other", RiskLevel.GREEN), now=datetime(2026, 1, 1))
    at_six = datetime(2026, 10, 26, 22, tzinfo=timezone.utc)
    assert assess_tool(tool("other", RiskLevel.YELLOW), now=at_six).level == RiskLevel.YELLOW
    assert assess_tool(tool("other", RiskLevel.YELLOW), now=NIGHT,
                       night_start_hour=22, night_end_hour=6).level == RiskLevel.RED


def test_server_configuration_controls_night_policy(monkeypatch):
    from app.risk import engine

    monkeypatch.setattr(engine.settings, "risk_night_start_hour", 22)
    monkeypatch.setattr(engine.settings, "risk_night_end_hour", 6)
    late_evening = datetime(2026, 10, 27, 14, tzinfo=timezone.utc)
    assert assess_tool(tool("other", RiskLevel.YELLOW), now=late_evening).level == RiskLevel.RED


@pytest.mark.parametrize(("start", "end"), [(24, 6), (-1, 6), (0, 0)])
def test_invalid_night_configuration_is_rejected(start, end):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_night_start_hour=start, risk_night_end_hour=end)


def test_invalid_tool_risk_cannot_be_downgraded():
    with pytest.raises(ValueError):
        assess_tool(tool("unknown", "green"), now=DAY)
