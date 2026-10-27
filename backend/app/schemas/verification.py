from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StartVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=256)


class VerifyCodeRequest(StartVerificationRequest):
    code: str = Field(min_length=1, max_length=32)


class VerificationResponse(BaseModel):
    action_id: int
    status: Literal["pending", "verified"]
    message: str
