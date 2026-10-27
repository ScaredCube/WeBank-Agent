from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrepareTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: int = Field(gt=0)
    recipient_name: str = Field(min_length=1, max_length=80)
    recipient_phone: str | None = Field(default=None, pattern=r"^1[0-9]{10}$")
    amount_fen: int = Field(gt=0, le=100_000_000_000)
    note: str = Field(default="", max_length=120)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("recipient_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("收款人不能为空")
        return value


class PrepareTransferResponse(BaseModel):
    transfer_id: int
    action_id: int
    risk_level: Literal["yellow", "red"]
    status: str
    confirmation_token: str | None
    message: str


class ExecuteTransferResponse(BaseModel):
    transfer_id: int
    status: Literal["completed"] = "completed"
    transaction_id: int
    balance_fen: int
    message: str = "模拟转账已完成。"
