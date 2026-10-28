from datetime import datetime

from pydantic import BaseModel

from app.schemas.wealth import WealthHoldingData, WealthRiskProfileData


class BankAccountData(BaseModel):
    account_id: int
    name: str
    masked_number: str
    currency: str
    balance_fen: int
    status: str
    card_status: str
    can_transfer: bool


class BankContactData(BaseModel):
    contact_id: int
    name: str
    bank_name: str
    masked_phone: str
    status: str
    can_transfer: bool


class BankDashboardData(BaseModel):
    accounts: list[BankAccountData]
    contacts: list[BankContactData]
    holdings: list[WealthHoldingData]
    risk_profile: WealthRiskProfileData
    generated_at: datetime
