from datetime import datetime

from typing import Literal, Annotated

from pydantic import model_validator

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
    card_result: dict | None = None


class AccountReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["account"]
    id: int = Field(gt=0)


class CardReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["card"]
    id: int = Field(gt=0)


class ContactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["contact"]
    id: int = Field(gt=0)


BankReference = Annotated[AccountReference | CardReference | ContactReference, Field(discriminator="kind")]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    references: list[BankReference] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def unique_kinds(self):
        kinds = [ref.kind for ref in self.references]
        if len(kinds) != len(set(kinds)):
            raise ValueError("同类金融对象每次只能引用一项")
        return self
