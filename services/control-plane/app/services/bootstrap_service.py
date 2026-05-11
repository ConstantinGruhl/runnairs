from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import InstanceSetting, Tenant, User, UserRole

BOOTSTRAP_STATE_KEY = "bootstrap_state"
BUILT_IN_AUTH_MODE = "built_in"
_INSECURE_JWT_SECRETS = {"", "devsecret", "changeme-dev-only"}


class BootstrapConflictError(ValueError):
    """Raised when bootstrap actions are requested in an invalid state."""


class BootstrapPermissionError(ValueError):
    """Raised when a caller is not allowed to continue bootstrap."""


class BootstrapValidationError(ValueError):
    """Raised when bootstrap completion requirements are not yet satisfied."""


def build_runtime_checks(db: Session) -> dict[str, bool]:
    return {
        "jwt_secret_valid": _jwt_secret_valid(),
        "platform_secrets_key_configured": bool(settings.platform_secrets_key.strip()),
        "database_ok": _database_ok(db),
    }


def summarize_bootstrap(
    *,
    stored: Mapping[str, Any] | None,
    checks: Mapping[str, bool],
) -> dict[str, Any]:
    payload = dict(stored or {})
    state = {
        "bootstrap_required": not bool(payload.get("completed_at")),
        "completed": bool(payload.get("completed_at")),
        "completed_at": payload.get("completed_at"),
        "admin_created": bool(payload.get("admin_user_id")),
        "instance_admin_user_id": payload.get("admin_user_id"),
        "instance_admin_email": payload.get("admin_email"),
        "tenant_id": payload.get("tenant_id"),
        "tenant_name": payload.get("tenant_name"),
        "notification_from_email": payload.get("notification_from_email"),
        "auth_mode": payload.get("auth_mode") or (BUILT_IN_AUTH_MODE if payload.get("admin_user_id") else None),
        "checks": dict(checks),
    }
    blocking_reasons = blocking_reasons_for_state(state)
    state["blocking_reasons"] = blocking_reasons
    state["ready_for_completion"] = not blocking_reasons
    return state


def blocking_reasons_for_state(state: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not state.get("admin_created"):
        reasons.append("bootstrap admin has not been created")
    if not state.get("tenant_name"):
        reasons.append("workspace name is missing")
    if not state.get("notification_from_email"):
        reasons.append("notification from email is missing")

    checks = state.get("checks", {})
    if not checks.get("jwt_secret_valid", False):
        reasons.append("JWT_SECRET is not safe for production")
    if not checks.get("platform_secrets_key_configured", False):
        reasons.append("PLATFORM_SECRETS_KEY is not configured")
    if not checks.get("database_ok", False):
        reasons.append("database connectivity check failed")
    return reasons


def validate_completion_state(state: Mapping[str, Any]) -> None:
    reasons = blocking_reasons_for_state(state)
    if reasons:
        raise BootstrapValidationError("; ".join(reasons))


def ensure_bootstrap_admin(state: Mapping[str, Any], *, user_id: str, role: str) -> None:
    admin_user_id = state.get("instance_admin_user_id")
    if not admin_user_id or role != UserRole.admin.value or admin_user_id != user_id:
        raise BootstrapPermissionError("only the bootstrap admin may continue setup")


def ensure_login_allowed(state: Mapping[str, Any], *, user_id: str, role: str) -> None:
    if not state.get("bootstrap_required"):
        return
    ensure_bootstrap_admin(state, user_id=user_id, role=role)


def bootstrap_required(db: Session) -> bool:
    return bool(get_bootstrap_state(db)["bootstrap_required"])


def get_bootstrap_state(db: Session) -> dict[str, Any]:
    return summarize_bootstrap(stored=_load_bootstrap_payload(db), checks=build_runtime_checks(db))


def initialize_instance(
    db: Session,
    *,
    tenant_name: str,
    admin_email: str,
    admin_password: str,
    notification_from_email: str,
) -> User:
    state = get_bootstrap_state(db)
    if state["admin_created"]:
        raise BootstrapConflictError("bootstrap admin already exists; sign in to resume setup")

    tenant = db.execute(select(Tenant).order_by(Tenant.created_at)).scalars().first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db.add(tenant)
        db.flush()
    else:
        tenant.name = tenant_name

    existing_admin = db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == admin_email)
    ).scalar_one_or_none()
    if existing_admin is not None:
        raise BootstrapConflictError(f"user {admin_email!r} already exists")

    admin = User(
        tenant_id=tenant.id,
        email=admin_email,
        password_hash=hash_password(admin_password),
        role=UserRole.admin,
    )
    db.add(admin)
    db.flush()

    payload = dict(_load_bootstrap_payload(db) or {})
    payload.update(
        {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "admin_user_id": str(admin.id),
            "admin_email": admin.email,
            "notification_from_email": notification_from_email,
            "auth_mode": BUILT_IN_AUTH_MODE,
            "completed_at": None,
        }
    )
    _save_bootstrap_payload(db, payload)
    return admin


def configure_instance(
    db: Session,
    *,
    user: User,
    tenant_name: str | None = None,
    notification_from_email: str | None = None,
) -> dict[str, Any]:
    state = get_bootstrap_state(db)
    if state["completed"]:
        raise BootstrapConflictError("bootstrap is already complete")
    ensure_bootstrap_admin(state, user_id=str(user.id), role=user.role.value)

    payload = dict(_load_bootstrap_payload(db) or {})
    if not payload.get("tenant_id"):
        raise BootstrapConflictError("bootstrap tenant has not been created yet")

    tenant = db.get(Tenant, uuid.UUID(str(payload["tenant_id"])))
    if tenant is None:
        raise BootstrapConflictError("bootstrap tenant is missing")

    if tenant_name is not None:
        tenant.name = tenant_name
        payload["tenant_name"] = tenant_name
    if notification_from_email is not None:
        payload["notification_from_email"] = notification_from_email

    payload.setdefault("auth_mode", BUILT_IN_AUTH_MODE)
    _save_bootstrap_payload(db, payload)
    return get_bootstrap_state(db)


def complete_bootstrap(db: Session, *, user: User) -> dict[str, Any]:
    state = get_bootstrap_state(db)
    if state["completed"]:
        raise BootstrapConflictError("bootstrap is already complete")
    ensure_bootstrap_admin(state, user_id=str(user.id), role=user.role.value)
    validate_completion_state(state)

    payload = dict(_load_bootstrap_payload(db) or {})
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_bootstrap_payload(db, payload)
    return get_bootstrap_state(db)


def seed_bootstrap_state(
    db: Session,
    *,
    tenant: Tenant,
    admin_user: User,
    notification_from_email: str,
) -> None:
    payload = dict(_load_bootstrap_payload(db) or {})
    payload.update(
        {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "admin_user_id": str(admin_user.id),
            "admin_email": admin_user.email,
            "notification_from_email": notification_from_email,
            "auth_mode": BUILT_IN_AUTH_MODE,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_bootstrap_payload(db, payload)


def _load_bootstrap_payload(db: Session) -> dict[str, Any] | None:
    row = db.execute(
        select(InstanceSetting).where(InstanceSetting.key == BOOTSTRAP_STATE_KEY)
    ).scalar_one_or_none()
    if row is None:
        return None
    return dict(row.value_json or {})


def _save_bootstrap_payload(db: Session, payload: Mapping[str, Any]) -> None:
    row = db.execute(
        select(InstanceSetting).where(InstanceSetting.key == BOOTSTRAP_STATE_KEY)
    ).scalar_one_or_none()
    if row is None:
        row = InstanceSetting(key=BOOTSTRAP_STATE_KEY, value_json=dict(payload))
        db.add(row)
        db.flush()
        return
    row.value_json = dict(payload)
    db.flush()


def _jwt_secret_valid() -> bool:
    if settings.app_env.lower() != "production":
        return True
    secret = settings.jwt_secret.strip()
    return secret not in _INSECURE_JWT_SECRETS and len(secret) >= 32


def _database_ok(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
