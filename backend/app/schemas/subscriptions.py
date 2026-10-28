from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class SubscriptionData(BaseModel):
    subscription_id: int
    merchant: str
    amount_fen: int
    cycle: str
    next_charge_date: date
    days_until_charge: int
    renewal_soon: bool
    status: str
    can_cancel: bool


class SubscriptionCandidateData(BaseModel):
    merchant: str
    amount_fen: int
    occurrences: int
    last_occurred_at: datetime
    suggested_cycle: str


class CancelSubscriptionPrepared(BaseModel):
    action_id: int
    subscription_id: int
    risk_level: Literal["yellow"]
    status: str
    confirmation_token: str | None
    message: str


class CancelSubscriptionResult(BaseModel):
    subscription_id: int
    status: Literal["cancelled"] = "cancelled"
    message: str = "模拟订阅已取消。"
