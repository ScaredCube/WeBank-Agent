from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User
from app.services.security_service import SecurityLocked, SecurityRateLimited, check_request

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    subject = decode_access_token(credentials.credentials)
    if subject is None or not subject.isdigit():
        raise unauthorized

    user = session.get(User, int(subject))
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def security_gate(user: CurrentUser) -> None:
    try:
        check_request(user.id)
    except SecurityLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except SecurityRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
