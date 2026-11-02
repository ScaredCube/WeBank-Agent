"""Validated, encrypted snapshots of server-issued bank results and receipts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.bills import MonthlyBill
from app.schemas.card_results import CardStatusSnapshot


class InternalTransferReceipt(BaseModel):
    """Server-confirmed, executed internal transfer only (never pending action)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    transfer_id: int = Field(gt=0)
    status: Literal["completed"]
    amount_fen: int = Field(gt=0)
    note: str = Field(max_length=200)
    source_name: str = Field(min_length=1, max_length=200)
    source_masked: str = Field(min_length=1, max_length=50)
    target_name: str = Field(min_length=1, max_length=200)
    target_masked: str = Field(min_length=1, max_length=50)
    balance_fen: int = Field(ge=0)
    currency: Literal["CNY"]
    transaction_id: int | None = Field(default=None, gt=0)


class ToolResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["monthly_bill", "card_status", "internal_transfer"]
    data: dict

    @model_validator(mode="after")
    def validate_data(self):
        if self.kind == "monthly_bill":
            self.data = MonthlyBill.model_validate(self.data).model_dump()
        elif self.kind == "card_status":
            self.data = CardStatusSnapshot.model_validate(self.data).model_dump()
        else:
            self.data = InternalTransferReceipt.model_validate(self.data).model_dump()
        return self


class ToolResultBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[ToolResultItem] = Field(min_length=1, max_length=8)
