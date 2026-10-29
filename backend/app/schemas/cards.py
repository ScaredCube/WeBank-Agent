from pydantic import BaseModel


class CardStatus(BaseModel):
    card_id: int
    account_name: str
    masked_number: str
    status: str
    account_status: str


class CardLossPrepared(BaseModel):
    action_id: int
    confirmation_token: str | None


class CardLossResult(BaseModel):
    card_id: int
    status: str
