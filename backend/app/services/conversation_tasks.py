"""Durable, bounded continuation of unfinished READ-ONLY banking requests.

Only canonical task facts are persisted, never raw chat text or authorization
tokens. The calling route must re-validate any bank object on every turn.
"""
from __future__ import annotations

from datetime import timedelta, timezone
import re
from typing import NamedTuple

from sqlmodel import Session, select

from app.core.time import utcnow
from app.models import ConversationTask

_READ_CUES = ("账单", "收支", "消费", "收入", "支出")
_QUERY_CUES = ("查", "看", "分析", "统计", "了解", "帮我", "给我")
_ACTION_CUES = ("转账", "汇款", "付款", "扣款", "挂失", "申购", "赎回",
                "转换", "卖出", "买入", "冻结", "取消订阅", "转给", "执行")
_MONTH = re.compile(r"(?<!\d)(20\d\d)[-/年](0?[1-9]|1[0-2])(?:月)?(?!\d)")
_RESUME = frozenset({
    "继续", "继续吧", "查吧", "查一下", "就这个", "就查这个",
    "用这个账户", "这个账户", "好的", "好", "可以", "开始吧",
    "就是它", "就它", "帮我查", "继续查",
})
_MAX_AGE = timedelta(hours=2)


class ReadGoal(NamedTuple):
    kind: str
    month: str | None

    @property
    def model_goal(self) -> str:
        month = self.month or "本月"
        if self.kind == "bill_analysis":
            return f"查询并分析所选账户{month}的收支与消费分类"
        return f"查询所选账户{month}的月度账单"


def classify_pending_read_goal(text: str) -> ReadGoal | None:
    """Only explicit read requests; never infer a pending financial write."""
    if (not isinstance(text, str) or len(text) > 4000
            or any(w in text for w in _ACTION_CUES)
            or not any(w in text for w in _READ_CUES)
            or not any(w in text for w in _QUERY_CUES)
            or any(term in text for term in ("什么是", "原理", "如何理解", "举个例子"))):
        return None
    match = _MONTH.search(text)
    month = f"{match.group(1)}-{int(match.group(2)):02d}" if match else None
    kind = "bill_analysis" if any(w in text for w in ("分析", "收支", "消费分类", "趋势")) else "bill_query"
    return ReadGoal(kind=kind, month=month)


def pending_task(session: Session, *, conversation_id: int, user_id: int) -> ConversationTask | None:
    task = session.exec(select(ConversationTask).where(
        ConversationTask.conversation_id == conversation_id,
        ConversationTask.user_id == user_id,
        ConversationTask.status == "needs_account",
    )).first()
    timestamp = task.updated_at.replace(tzinfo=timezone.utc) if task and task.updated_at.tzinfo is None else (task.updated_at if task else None)
    if task and utcnow() - timestamp > _MAX_AGE:
        task.status = "expired"
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
        return None
    return task


def can_resume_task(text: str) -> bool:
    """A brief completion of prior context, not an unrelated fresh instruction."""
    if not isinstance(text, str) or any(w in text for w in _ACTION_CUES):
        return False
    return text.strip().rstrip("。！!?？ ").strip() in _RESUME


def remember_pending_task(session: Session, *, conversation_id: int,
                          user_id: int, goal: ReadGoal) -> None:
    task = session.get(ConversationTask, conversation_id)
    if task is None:
        task = ConversationTask(conversation_id=conversation_id, user_id=user_id)
    if task.user_id != user_id:
        raise ValueError("Conversation task owner mismatch")
    task.kind = goal.kind
    task.month = goal.month
    task.status = "needs_account"
    task.updated_at = utcnow()
    session.add(task)
    session.commit()


def mark_task_completed(session: Session, *, conversation_id: int, user_id: int) -> None:
    task = session.get(ConversationTask, conversation_id)
    if task is None or task.user_id != user_id or task.status != "needs_account":
        return
    task.status = "completed"
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
