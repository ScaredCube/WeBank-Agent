from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    request_id: str
    conversation_id: int | None
    action_id: int | None
    transfer_id: int | None
    transaction_id: int | None
    event_type: str
    tool: str | None
    risk_level: str | None
    reason_codes: str | None
    result: str | None
    created_at: datetime
