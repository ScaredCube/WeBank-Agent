from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.agent.registry import RiskLevel, ToolSpec
from app.core.config import settings

_ORDER = {RiskLevel.GREEN: 0, RiskLevel.YELLOW: 1, RiskLevel.RED: 2}
_LOCAL_TIMEZONE = timezone(timedelta(hours=8))
_TRANSFER_NAME = "transfer"
_TRANSFER_LIMIT_FEN = 100_000


@dataclass(frozen=True)
class RiskDecision:
    level: RiskLevel
    reasons: tuple[str, ...]


def assess_tool(
    spec: ToolSpec,
    *,
    now: datetime | None = None,
    amount_fen: int | None = None,
    daily_total_fen: int | None = None,
    night_start_hour: int | None = None,
    night_end_hour: int | None = None,
) -> RiskDecision:
    """Assess trusted server-side context; daily_total excludes this transaction.

    A future transfer service must obtain the daily total from its own database,
    never from model-supplied arguments. Decisions do not execute any tool.
    """
    if not isinstance(spec.risk, RiskLevel):
        raise ValueError("无效的工具风险等级")
    if night_start_hour is None:
        night_start_hour = settings.risk_night_start_hour
    if night_end_hour is None:
        night_end_hour = settings.risk_night_end_hour
    if any(type(hour) is not int or not 0 <= hour <= 23
           for hour in (night_start_hour, night_end_hour)) or night_start_hour == night_end_hour:
        raise ValueError("无效的夜间时段")
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("风险判定时间必须包含时区")

    level = spec.risk
    reasons = ["工具基础风险等级"]
    if spec.name == _TRANSFER_NAME:
        if (type(amount_fen) is not int or amount_fen <= 0
                or type(daily_total_fen) is not int or daily_total_fen < 0):
            raise ValueError("转账金额和日累计金额无效")
        transfer_level = (RiskLevel.RED if daily_total_fen + amount_fen > _TRANSFER_LIMIT_FEN
                          else RiskLevel.YELLOW)
        if _ORDER[transfer_level] > _ORDER[level]:
            level = transfer_level
        reasons.append("转账日累计超过限额" if transfer_level == RiskLevel.RED else "转账需要确认")

    hour = now.astimezone(_LOCAL_TIMEZONE).hour
    night = (night_start_hour <= hour < night_end_hour if night_start_hour < night_end_hour
             else hour >= night_start_hour or hour < night_end_hour)
    if level == RiskLevel.YELLOW and night:
        level = RiskLevel.RED
        reasons.append("夜间操作升级")
    return RiskDecision(level=level, reasons=tuple(reasons))
