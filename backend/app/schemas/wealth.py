from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WealthProductData(BaseModel):
    product_id: int
    name: str
    category: str
    risk_level: str
    expected_rate_bps: int
    term_days: int
    min_amount_fen: int
    status: str


class WealthHoldingData(BaseModel):
    holding_id: int
    product_id: int
    product_name: str
    category: str
    risk_level: str
    expected_rate_bps: int
    amount_fen: int
    yesterday_earnings_fen: int
    status: str


class WealthRiskProfileData(BaseModel):
    risk_level: str
    score: int
    assessed_at: datetime | None = None


class AssessWealthRiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answers: list[int] = Field(min_length=3, max_length=3)

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, value: list[int]) -> list[int]:
        if any(type(item) is not int or not 0 <= item <= 3 for item in value):
            raise ValueError("风险测评分值无效")
        return value


class AssessWealthRiskResponse(WealthRiskProfileData):
    message: str = "风险测评已保存。"


class PrepareWealthSubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: int = Field(gt=0)
    account_id: int | None = Field(default=None, gt=0)
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        return value.strip()


class PrepareWealthRedeemRequest(PrepareWealthSubscribeRequest):
    pass


class WealthOrderPrepared(BaseModel):
    order_id: int
    action_id: int
    risk_level: Literal["red"]
    status: str
    confirmation_token: str | None
    message: str


class ExecuteWealthOrderResponse(BaseModel):
    order_id: int
    order_type: Literal["subscribe", "redeem"]
    status: Literal["completed"] = "completed"
    transaction_id: int
    balance_fen: int
    holding_fen: int
    message: str = "模拟理财操作已完成。"
