from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConfirmActionRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class ConfirmActionResponse(BaseModel):
    id: int
    status: str
    message: str


class PendingActionResponse(BaseModel):
    id: int
    action_type: str
    details: dict[str, Any]
    risk_level: str
    status: Literal["pending", "confirmed", "cancelled", "expired", "verified"]
    created_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None


class CancelActionResponse(BaseModel):
    id: int
    status: Literal["cancelled"] = "cancelled"
    message: str = "已取消，操作未执行。"
