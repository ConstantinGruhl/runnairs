from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import SESSION_COOKIE_NAME, decode_token
from app.models import User
from app.services import auth_service

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    request: Request,
    token: Annotated[str | None, Depends(_oauth2)],
) -> User:
    raw_token = token or request.cookies.get(SESSION_COOKIE_NAME)

    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    if not token:
        token = raw_token
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing subject")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    try:
        auth_service.ensure_user_can_authenticate(user)
        auth_service.ensure_session_version(user, payload.get("session_version"))
    except auth_service.AuthPermissionError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: str):
    allowed = set(roles)

    def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{user.role}' not in {sorted(allowed)}",
            )
        return user

    return _check
