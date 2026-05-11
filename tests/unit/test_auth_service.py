from __future__ import annotations

import uuid

import pytest

from app.core.security import verify_password
from app.models import User, UserRole, UserStatus
from app.services import auth_service


def _user() -> User:
    return User(
        tenant_id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="placeholder",
        role=UserRole.admin,
        status=UserStatus.active,
        session_version=1,
    )


def test_validate_password_strength_accepts_letters_and_numbers() -> None:
    auth_service.validate_password_strength("Strongpass123")


def test_validate_password_strength_rejects_weak_passwords() -> None:
    with pytest.raises(auth_service.AuthValidationError, match="at least 12 characters"):
        auth_service.validate_password_strength("weakpass")


def test_recovery_code_consumption_rotates_session_and_clears_code() -> None:
    user = _user()
    auth_service.set_password(user, "Strongpass123", increment_session_version=False)
    code = auth_service.issue_recovery_code(user)

    previous_session_version = user.session_version
    auth_service.consume_recovery_code(
        user,
        code=code,
        new_password="Recoveredpass456",
    )

    assert user.session_version == previous_session_version + 1
    assert user.recovery_code_hash is None
    assert user.recovery_code_expires_at is None
    assert verify_password("Recoveredpass456", user.password_hash)


def test_password_reset_code_must_match_and_not_be_expired() -> None:
    user = _user()
    auth_service.set_password(user, "Strongpass123", increment_session_version=False)
    code = auth_service.issue_password_reset_code(user)

    auth_service.consume_password_reset_code(
        user,
        code=code,
        new_password="Resetpass456",
    )

    assert user.must_reset_password is False
    assert user.password_reset_code_hash is None
    assert user.password_reset_code_expires_at is None
    assert verify_password("Resetpass456", user.password_hash)


def test_is_built_in_login_allowed_returns_true_for_built_in_mode() -> None:
    state = {"auth_mode": "built_in", "instance_admin_email": "admin@example.com"}
    assert auth_service.is_built_in_login_allowed(state, email="anyone@example.com") is True


def test_is_built_in_login_allowed_returns_true_for_hybrid_mode() -> None:
    state = {"auth_mode": "hybrid", "instance_admin_email": "admin@example.com"}
    assert auth_service.is_built_in_login_allowed(state, email="anyone@example.com") is True


def test_is_built_in_login_allowed_only_allows_bootstrap_admin_in_oidc_mode() -> None:
    state = {"auth_mode": "oidc", "instance_admin_email": "boot@example.com"}
    assert auth_service.is_built_in_login_allowed(state, email="boot@example.com") is True
    assert auth_service.is_built_in_login_allowed(state, email="BOOT@example.com") is True
    assert auth_service.is_built_in_login_allowed(state, email="someone-else@example.com") is False


def test_is_built_in_login_allowed_returns_false_when_no_bootstrap_admin_recorded() -> None:
    state = {"auth_mode": "oidc", "instance_admin_email": None}
    assert auth_service.is_built_in_login_allowed(state, email="boot@example.com") is False
