"""Only the actual server-executed green transfer may become a durable receipt."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.tool_results import InternalTransferReceipt, ToolResultBundle


SAMPLE = {
    "transfer_id": 12, "status": "completed", "amount_fen": 50000,
    "note": "", "source_name": "日常账户", "source_masked": "**** 0011",
    "target_name": "备用账户", "target_masked": "**** 0022",
    "balance_fen": 450000, "currency": "CNY", "transaction_id": 21,
}


def test_completed_receipt_is_strict_and_can_be_part_of_history_bundle():
    result = ToolResultBundle.model_validate({"items": [
        {"kind": "internal_transfer", "data": SAMPLE}
    ]})
    assert result.items[0].data == SAMPLE
    assert InternalTransferReceipt.model_validate(SAMPLE).model_dump() == SAMPLE


@pytest.mark.parametrize("patch", [
    {"status": "pending"},
    {"status": "confirmed"},
    {"status": "failed"},
    {"amount_fen": "50000"},
    {"amount_fen": -10},
    {"transfer_id": 0},
    {"currency": "USD"},
    {"transaction_id": -1},
    {"confirmation_token": "must-never-appear"},
])
def test_untrusted_or_pending_receipt_cannot_be_persisted(patch):
    payload = deepcopy(SAMPLE)
    payload.update(patch)
    with pytest.raises(ValidationError):
        ToolResultBundle.model_validate({
            "items": [{"kind": "internal_transfer", "data": payload}]
        })


def test_existing_bill_and_card_kinds_stay_separate():
    with pytest.raises(ValidationError):
        ToolResultBundle.model_validate({
            "items": [{"kind": "internal_transfer", "data": {"status": "completed"}}]
        })
