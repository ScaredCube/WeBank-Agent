"""Explain a narrowly scoped question about an earlier authenticated bill snapshot.

This does not re-authorize a bank operation or promote chat text into data.
The account selection is re-validated at the HTTP boundary on every turn.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.agent.bill_insights import summarize_bill_insights
from app.models import Conversation, Message, MessageResult
from app.schemas.bills import MonthlyBill
from app.schemas.tool_results import ToolResultBundle
from app.services.vault import VaultError, decrypt_result_snapshot


_ANCHORS = ("刚才", "上次", "之前", "前面", "上一轮", "那份", "这份")
_CATEGORY = ("分类", "类别", "哪类", "哪些支出", "最高", "最多", "值得关注")
_EXCLUDE = ("转账", "付款", "赎回", "申购", "挂失", "冻结", "取消",
            "为什么", "原因", "变化", "增长", "比较", "对比", "趋势",
            "上个月", "下个月", "交易明细", "逐笔", "每笔")


def asks_about_previous_bill_categories(text: str) -> bool:
    if not isinstance(text, str) or len(text) > 240:
        return False
    return (any(part in text for part in _ANCHORS)
            and any(part in text for part in ("账单", "消费"))
            and any(part in text for part in _CATEGORY)
            and not any(part in text for part in _EXCLUDE)
            and not any(char.isdigit() for char in text))


def verified_previous_bill_summary(session: Session, *, conversation_id: int,
                                  user_id: int, masked_number: str,
                                  account_name: str, selection_time: datetime) -> str | None:
    """Read one saved server-authored encrypted snapshot; never use chat prose."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        return None
    snapshots = session.exec(
        select(MessageResult)
        .join(Message, MessageResult.message_id == Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(MessageResult.message_id.desc()).limit(12)
    ).all()
    cutoff = (selection_time.replace(tzinfo=timezone.utc) if selection_time.tzinfo is None
              else selection_time.astimezone(timezone.utc))
    for record in snapshots:
        created = (record.created_at.replace(tzinfo=timezone.utc)
                   if record.created_at.tzinfo is None
                   else record.created_at.astimezone(timezone.utc))
        if created < cutoff:
            continue
        if record.kind not in {"monthly_bill", "tool_results"}:
            continue
        try:
            data = decrypt_result_snapshot(record.ciphertext, record.key_version)
            if record.kind == "monthly_bill":
                bills = [data]
            else:
                bundle = ToolResultBundle.model_validate(data)
                bills = [item.data for item in bundle.items if item.kind == "monthly_bill"]
            for candidate in reversed(bills):
                bill = MonthlyBill.model_validate(candidate)
                if (bill.masked_number != masked_number or
                        bill.account_name != account_name or bill.currency != "CNY"):
                    continue
                result = summarize_bill_insights([
                    ("get_monthly_bill", {"ok": True, "data": bill.model_dump()})
                ], "分析本月消费分类")
                if result:
                    return ("根据这段会话此前已核验并保存的账单：" + result
                            + "如需本月最新数据，可以重新查询。")
        except (VaultError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return None
