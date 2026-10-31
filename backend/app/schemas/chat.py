from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=120)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime
    bill_result: dict | None = None


class AccountReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["account"]
    id: int = Field(gt=0)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    references: list[AccountReference] = Field(default_factory=list, max_length=1)
