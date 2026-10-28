from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=32)


class UnlockResponse(BaseModel):
    status: Literal["unlocked"]
    message: str
