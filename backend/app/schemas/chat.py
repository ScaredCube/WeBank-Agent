from datetime import datetime

from typing import Literal, Annotated

from pydantic import model_validator

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.generative_ui import ViewContext


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=60)

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
    tool_results: list[dict] | None = None
    ui_view: dict | None = None


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


class HoldingReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["holding"]
    id: int = Field(gt=0)


BankReference = Annotated[
    AccountReference | CardReference | ContactReference | HoldingReference,
    Field(discriminator="kind"),
]

IntentAction = Literal[
    "transfer", "internal_transfer", "collect", "purchase", "redeem", "convert",
]


class IntentEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["account", "contact", "holding"]
    id: int = Field(gt=0)


class ChatIntent(BaseModel):
    """Local drag intent. Only entity IDs cross the boundary; the server mints
    tokens and renders the prompt. Labels and tokens are never accepted here."""
    model_config = ConfigDict(extra="forbid", strict=True)
    action: IntentAction
    source: IntentEntity
    target: IntentEntity

    @model_validator(mode="after")
    def distinct_entities(self):
        if self.source.kind == self.target.kind and self.source.id == self.target.id:
            raise ValueError("来源与目标不能是同一实体")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    references: list[BankReference] = Field(default_factory=list, max_length=3)
    intent: ChatIntent | None = None
    view_context: ViewContext | None = None
    # Required for retriable clients; optional for backwards-compatible legacy calls.
    request_id: str | None = Field(default=None, min_length=8, max_length=64,
                                   pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def unique_kinds(self):
        kinds = [ref.kind for ref in self.references]
        if len(kinds) != len(set(kinds)):
            raise ValueError("同类金融对象每次只能引用一项")
        return self
