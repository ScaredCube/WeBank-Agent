"""Allowlisted, token-free financial card snapshot from a GREEN bank tool."""
from pydantic import BaseModel, ConfigDict, Field


class CardSnapshotItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    card_id: int = Field(gt=0)
    account_name: str = Field(max_length=120)
    masked_number: str = Field(max_length=90)
    status: str = Field(max_length=30)
    account_status: str = Field(max_length=30)


class CardStatusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cards: list[CardSnapshotItem] = Field(max_length=30)


def from_card_tool_result(data: list[dict]) -> CardStatusSnapshot:
    """Never copy account_token or additional tool fields into the browser or database."""
    if not isinstance(data, list) or len(data) > 30:
        raise ValueError("invalid card result")
    return CardStatusSnapshot(cards=[
        CardSnapshotItem.model_validate({key: row[key] for key in
            ("card_id", "account_name", "masked_number", "status", "account_status")})
        for row in data
    ])
