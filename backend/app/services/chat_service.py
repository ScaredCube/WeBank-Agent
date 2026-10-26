from sqlmodel import Session, col, select

from app.core.time import utcnow
from app.models import Conversation, Message, User


def list_conversations(session: Session, user: User) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(col(Conversation.updated_at).desc())
    )
    return list(session.exec(statement).all())


def create_conversation(session: Session, user: User, title: str = "新对话") -> Conversation:
    conversation = Conversation(user_id=user.id, title=title)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def get_conversation(session: Session, user: User, conversation_id: int) -> Conversation | None:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    )
    return session.exec(statement).first()


def list_messages(session: Session, conversation_id: int) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(col(Message.id))
    )
    return list(session.exec(statement).all())


def recent_messages(session: Session, conversation_id: int, limit: int) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(col(Message.id).desc())
        .limit(limit)
    )
    return list(reversed(list(session.exec(statement).all())))


def append_message(session: Session, conversation: Conversation, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role=role, content=content)
    session.add(message)
    conversation.updated_at = utcnow()
    session.commit()
    session.refresh(message)
    return message


def derive_title(content: str) -> str:
    title = " ".join(content.split())
    return title[:24] if title else "新对话"
