"""Validated snapshots of server-issued, read-only tool results."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.bills import MonthlyBill
from app.schemas.card_results import CardStatusSnapshot


class ToolResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["monthly_bill", "card_status"]
    data: dict

    @model_validator(mode="after")
    def validate_data(self):
        if self.kind == "monthly_bill":
            self.data = MonthlyBill.model_validate(self.data).model_dump()
        else:
            self.data = CardStatusSnapshot.model_validate(self.data).model_dump()
        return self


class ToolResultBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[ToolResultItem] = Field(min_length=1, max_length=8)
