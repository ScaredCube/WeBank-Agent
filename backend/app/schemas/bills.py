from pydantic import BaseModel


class BillCategory(BaseModel):
    category: str
    amount_fen: int
    count: int


class BillAnomaly(BaseModel):
    status: str = "需核对"
    reason: str
    counterparty: str
    amount_fen: int
    occurred_at: str
    previous_occurred_at: str


class MonthlyBill(BaseModel):
    month: str
    account_name: str
    masked_number: str
    currency: str
    income_fen: int
    expense_fen: int
    consumption_fen: int
    consumption_count: int
    transfer_out_fen: int
    transfer_out_count: int
    transfer_in_fen: int
    transfer_in_count: int
    investment_out_fen: int = 0
    investment_out_count: int = 0
    investment_in_fen: int = 0
    investment_in_count: int = 0
    categories: list[BillCategory]
    anomalies: list[BillAnomaly]
    ignored_count: int
