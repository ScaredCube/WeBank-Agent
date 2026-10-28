from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import CurrentUser, SessionDep
from app.schemas.bills import MonthlyBill
from app.services.audit_service import record
from app.services.bill_service import BillError, monthly_bill

router = APIRouter(prefix="/bills", tags=["bills"])


@router.get("/monthly", response_model=MonthlyBill)
def get_monthly_bill(response: Response, session: SessionDep, user: CurrentUser,
                     month: str | None = None, account_id: int | None = Query(default=None, gt=0)) -> MonthlyBill:
    response.headers["Cache-Control"] = "no-store"
    record(session, user_id=user.id, event_type="tool_called", tool="get_monthly_bill", result="success")
    try:
        bill = monthly_bill(session, user.id, month, account_id)
    except BillError as exc:
        record(session, user_id=user.id, event_type="tool_result", tool="get_monthly_bill", result="denied")
        session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record(session, user_id=user.id, event_type="risk_assessed", tool="get_monthly_bill",
           risk_level="green", reasons=("工具基础风险等级",), result="success")
    record(session, user_id=user.id, event_type="tool_result", tool="get_monthly_bill", result="success")
    session.commit()
    return bill
