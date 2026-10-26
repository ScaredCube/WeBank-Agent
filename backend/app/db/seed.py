from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import hash_password
from app.models import User


def seed_demo_user(session: Session) -> User:
    user = session.exec(select(User).where(User.username == settings.demo_username)).first()
    if user:
        return user

    user = User(
        username=settings.demo_username,
        password_hash=hash_password(settings.demo_password),
        display_name=settings.demo_display_name,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
