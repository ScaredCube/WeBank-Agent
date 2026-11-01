"""Read-only conversational continuity grounded in explicit prior bank selections.

Selection IDs have no authority by themselves: the caller revalidates ownership,
status and the current user on every follow-up. No write/prepare operation may
inherit an old selection.
"""
from sqlmodel import Session, select

from app.models import ConversationSelection, Message, MessageResult
from app.core.time import utcnow
from app.services.vault import VaultError, decrypt_result_snapshot
from app.schemas.tool_results import ToolResultBundle


_READ_ONLY_CUES = ("账单", "消费", "收入", "支出", "卡片状态", "银行卡状态",
                   "上个月", "下个月", "前一个月", "这个月", "本月",
                   "对比", "相比", "比较", "再查", "继续查", "刚才那张卡")
_WRITE_CUES = ("转账", "汇款", "打款", "挂失", "冻结", "解冻", "申购", "赎回",
               "支付", "付款", "扣款", "取消订阅", "修改限额")
_OTHER_OBJECT = ("另一个账户", "另一张卡", "其他账户", "换个账户", "另一账户")


def allow_readonly_followup(text: str) -> bool:
    return (any(cue in text for cue in _READ_ONLY_CUES)
            and not any(cue in text for cue in _WRITE_CUES + _OTHER_OBJECT))


def remember_selection(session: Session, *, conversation_id: int, user_id: int,
                       account_id: int, card_id: int | None) -> None:
    existing = session.get(ConversationSelection, conversation_id)
    if existing is None:
        session.add(ConversationSelection(
            conversation_id=conversation_id, user_id=user_id,
            account_id=account_id, card_id=card_id))
    else:
        if existing.user_id != user_id:
            raise ValueError("Conversation ownership conflict")
        existing.account_id = account_id
        existing.card_id = card_id
        existing.updated_at = utcnow()
        session.add(existing)
    session.commit()


def previously_selected(session: Session, *, conversation_id: int,
                        user_id: int) -> ConversationSelection | None:
    return session.exec(select(ConversationSelection).where(
        ConversationSelection.conversation_id == conversation_id,
        ConversationSelection.user_id == user_id,
    )).first()


def latest_trusted_bill_month(session: Session, *, conversation_id: int) -> tuple[str, str] | None:
    """Only server-generated encrypted snapshots may provide previous bill month."""
    snapshots = session.exec(
        select(MessageResult)
        .join(Message, MessageResult.message_id == Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(MessageResult.message_id.desc())
        .limit(12)
    ).all()
    for snapshot in snapshots:
        try:
            payload = decrypt_result_snapshot(snapshot.ciphertext, snapshot.key_version)
            if snapshot.kind == "monthly_bill":
                month = payload.get("month") if isinstance(payload, dict) else None
                number = payload.get("masked_number") if isinstance(payload, dict) else None
                if isinstance(month, str) and isinstance(number, str):
                    return month, number
            if snapshot.kind == "tool_results":
                bundle = ToolResultBundle.model_validate(payload)
                for item in reversed(bundle.items):
                    if item.kind == "monthly_bill":
                        month = item.data.get("month")
                        number = item.data.get("masked_number")
                        if isinstance(month, str) and isinstance(number, str):
                            return month, number
        except (VaultError, ValueError, AttributeError, TypeError):
            continue
    return None
