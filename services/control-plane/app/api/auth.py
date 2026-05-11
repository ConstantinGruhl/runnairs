from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.core.security import verify_password
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    PasswordResetCompleteRequest,
    RecoveryCompleteRequest,
    TokenResponse,
    UserPublic,
)
from app.services import auth_service, bootstrap_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    try:
        user = auth_service.ensure_user_can_authenticate(user)
    except auth_service.AuthPermissionError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    try:
        bootstrap_service.ensure_login_allowed(
            bootstrap_service.get_bootstrap_state(db),
            user_id=str(user.id),
            role=user.role.value,
        )
    except bootstrap_service.BootstrapPermissionError as exc:
        raise HTTPException(status.HTTP_423_LOCKED, str(exc)) from exc

    token = auth_service.create_session_token(user)
    auth_service.set_session_cookie(response, token)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.status_code = status.HTTP_204_NO_CONTENT
    auth_service.clear_session_cookie(response)
    return response


@router.post("/password-reset/complete", response_model=TokenResponse)
def complete_password_reset(
    payload: PasswordResetCompleteRequest,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    try:
        auth_service.consume_password_reset_code(
            user,
            code=payload.reset_code,
            new_password=payload.new_password,
        )
    except (auth_service.AuthValidationError, auth_service.AuthPermissionError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    db.commit()
    db.refresh(user)
    token = auth_service.create_session_token(user)
    auth_service.set_session_cookie(response, token)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post("/recovery/complete", response_model=TokenResponse)
def complete_recovery(
    payload: RecoveryCompleteRequest,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    try:
        auth_service.consume_recovery_code(
            user,
            code=payload.recovery_code,
            new_password=payload.new_password,
        )
    except (auth_service.AuthValidationError, auth_service.AuthPermissionError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    db.commit()
    db.refresh(user)
    token = auth_service.create_session_token(user)
    auth_service.set_session_cookie(response, token)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))
