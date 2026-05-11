from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.core.config import settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User, UserStatus

PASSWORD_MIN_LENGTH = 12
PASSWORD_RESET_TTL = timedelta(hours=2)


class AuthValidationError(ValueError):
    """Raised when auth-related input fails validation."""


class AuthPermissionError(ValueError):
    """Raised when a user may not authenticate or complete an auth flow."""


def validate_password_strength(password: str) -> None:
    normalized = password.strip()
    reasons: list[str] = []
    if len(normalized) < PASSWORD_MIN_LENGTH:
        reasons.append(f"password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if not any(char.isalpha() for char in normalized):
        reasons.append("password must include at least one letter")
    if not any(char.isdigit() for char in normalized):
        reasons.append("password must include at least one number")
    if any(char.isspace() for char in password):
        reasons.append("password must not contain whitespace")

    if reasons:
        raise AuthValidationError("; ".join(reasons))


def create_session_token(user: User) -> str:
    return create_access_token(
        subject=str(user.id),
        role=user.role.value,
        tenant_id=str(user.tenant_id),
        extra={"session_version": user.session_version},
    )


def set_session_cookie(response: Response, token: str) -> None:
    max_age = settings.jwt_ttl_minutes * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.app_env.lower() == "production",
        samesite="lax",
        path="/",
    )


def ensure_user_can_authenticate(user: User | None) -> User:
    if user is None:
        raise AuthPermissionError("invalid credentials")
    if user.status != UserStatus.active:
        raise AuthPermissionError("account is disabled")
    return user


def ensure_session_version(user: User, token_session_version: int | None) -> None:
    if token_session_version is None or int(token_session_version) != user.session_version:
        raise AuthPermissionError("session has expired; sign in again")


def set_password(user: User, password: str, *, increment_session_version: bool) -> None:
    validate_password_strength(password)
    user.password_hash = hash_password(password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.must_reset_password = False
    if user.session_version is None:
        user.session_version = 1
    if increment_session_version:
        user.session_version += 1


def issue_recovery_code(user: User) -> str:
    code = generate_one_time_code()
    user.recovery_code_hash = hash_password(code)
    user.recovery_code_expires_at = None
    return code


def consume_recovery_code(user: User, *, code: str, new_password: str) -> None:
    ensure_user_can_authenticate(user)
    if not user.recovery_code_hash or not verify_password(code, user.recovery_code_hash):
        raise AuthValidationError("recovery code is invalid")

    set_password(user, new_password, increment_session_version=True)
    user.recovery_code_hash = None
    user.recovery_code_expires_at = None


def issue_password_reset_code(user: User) -> str:
    code = generate_one_time_code()
    user.password_reset_code_hash = hash_password(code)
    user.password_reset_code_expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TTL
    user.must_reset_password = True
    return code


def consume_password_reset_code(user: User, *, code: str, new_password: str) -> None:
    ensure_user_can_authenticate(user)
    expires_at = user.password_reset_code_expires_at
    if (
        not user.password_reset_code_hash
        or not expires_at
        or expires_at < datetime.now(timezone.utc)
        or not verify_password(code, user.password_reset_code_hash)
    ):
        raise AuthValidationError("password reset code is invalid or expired")

    set_password(user, new_password, increment_session_version=True)
    user.password_reset_code_hash = None
    user.password_reset_code_expires_at = None


def generate_one_time_code() -> str:
    raw = secrets.token_hex(12).upper()
    return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))
