from __future__ import annotations

from app.models import User, UserRole, UserStatus
from app.services import auth_service


class UserManagementConflictError(ValueError):
    """Raised when a user-management action conflicts with current state."""


class UserManagementValidationError(ValueError):
    """Raised when a user-management request is invalid."""


def list_users_for_tenant(*, actor: User, users: list[User]) -> list[User]:
    return [user for user in users if user.tenant_id == actor.tenant_id]


def create_user(
    *,
    actor: User,
    email: str,
    password: str,
    role: UserRole,
    existing_user: User | None,
) -> User:
    if existing_user is not None:
        raise UserManagementConflictError(f"user {email!r} already exists")

    user = User(
        tenant_id=actor.tenant_id,
        email=email,
        password_hash="",
        role=role,
        status=UserStatus.active,
    )
    auth_service.set_password(user, password, increment_session_version=False)
    return user


def update_user(
    *,
    actor: User,
    target: User,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    active_admin_count: int,
) -> None:
    if actor.tenant_id != target.tenant_id:
        raise UserManagementValidationError("user belongs to a different tenant")
    if actor.id == target.id:
        if status == UserStatus.disabled:
            raise UserManagementValidationError("you cannot disable your own account")
        if role is not None and role != UserRole.admin:
            raise UserManagementValidationError("you cannot remove your own admin role")

    next_role = role or target.role
    next_status = status or target.status

    if target.role == UserRole.admin and target.status == UserStatus.active:
        removing_active_admin = next_role != UserRole.admin or next_status != UserStatus.active
        if removing_active_admin and active_admin_count <= 1:
            raise UserManagementValidationError("the last active admin account cannot be removed or disabled")

    if role is not None:
        target.role = role
    if status is not None and status != target.status:
        target.status = status
        if status == UserStatus.disabled:
            target.session_version += 1


def issue_password_reset(*, target: User) -> tuple[str, str | None]:
    code = auth_service.issue_password_reset_code(target)
    expires_at = target.password_reset_code_expires_at.isoformat() if target.password_reset_code_expires_at else None
    return code, expires_at


def issue_recovery_code(*, target: User) -> tuple[str, str | None]:
    code = auth_service.issue_recovery_code(target)
    expires_at = target.recovery_code_expires_at.isoformat() if target.recovery_code_expires_at else None
    return code, expires_at
