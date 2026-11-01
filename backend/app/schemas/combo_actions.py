from pydantic import BaseModel, Field


class InternalTransferExecuteResponse(BaseModel):
    transfer_id: int
    status: str = Field(pattern=r"^completed$")
    amount_fen: int
    note: str = ""
    source_name: str
    source_masked: str
    target_name: str
    target_masked: str
    balance_fen: int
    currency: str = "CNY"
    transaction_id: int | None = None


class CollectionExecuteResponse(BaseModel):
    collection_id: int
    status: str = Field(pattern=r"^completed$")


class ConversionExecuteResponse(BaseModel):
    conversion_id: int
    status: str = Field(pattern=r"^completed$")
    amount_fen: int
    source_product_name: str
    target_product_name: str
    source_holding_fen: int
    target_holding_fen: int
