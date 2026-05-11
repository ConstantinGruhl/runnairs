from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import auth_service
from app.models import InstanceSetting, OidcProvider, Tenant, User, UserRole

BOOTSTRAP_STATE_KEY = "bootstrap_state"
BUILT_IN_AUTH_MODE = "built_in"
HYBRID_AUTH_MODE = "hybrid"
OIDC_AUTH_MODE = "oidc"
SUPPORTED_AUTH_MODES = (BUILT_IN_AUTH_MODE, HYBRID_AUTH_MODE, OIDC_AUTH_MODE)
AUTH_MODES_REQUIRING_OIDC_PROVIDER = (HYBRID_AUTH_MODE, OIDC_AUTH_MODE)
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
    provider_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(stored or {})
    auth_mode = payload.get("auth_mode")
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
        "auth_mode": auth_mode,
        "supported_auth_modes": list(SUPPORTED_AUTH_MODES),
        "checks": dict(checks),
        "oidc_provider_state": dict(provider_state or {"exists": False, "is_enabled": False, "name": None}),
        "built_in_login_enabled": auth_mode != OIDC_AUTH_MODE,
    }
    blocking_reasons = blocking_reasons_for_state(state)
    state["blocking_reasons"] = blocking_reasons
    state["ready_for_completion"] = not blocking_reasons
    state["operator_guidance"] = operator_guidance_for_state(state)
    return state


def blocking_reasons_for_state(state: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not state.get("admin_created"):
        reasons.append("bootstrap admin has not been created")
    if not state.get("tenant_name"):
        reasons.append("workspace name is missing")
    if not state.get("notification_from_email"):
        reasons.append("notification from email is missing")
    if not state.get("auth_mode"):
        reasons.append("authentication mode has not been selected")

    checks = state.get("checks", {})
    if not checks.get("jwt_secret_valid", False):
        reasons.append("JWT_SECRET is not safe for production")
    if not checks.get("platform_secrets_key_configured", False):
        reasons.append("PLATFORM_SECRETS_KEY is not configured")
    if not checks.get("database_ok", False):
        reasons.append("database connectivity check failed")
    return reasons


def operator_guidance_for_state(state: Mapping[str, Any]) -> list[dict[str, str]]:
    guidance: list[dict[str, str]] = []
    checks = state.get("checks", {})

    if not state.get("admin_created"):
        guidance.append(
            {
                "key": "bootstrap_admin_missing",
                "category": "setup",
                "title": "Create the bootstrap admin",
                "body": "A fresh instance needs one admin account to own the initial workspace and finish configure mode.",
                "action": "Use the setup form below to create the first admin account before attempting normal platform access.",
            }
        )
    if not state.get("tenant_name"):
        guidance.append(
            {
                "key": "tenant_name_missing",
                "category": "setup",
                "title": "Choose a workspace name",
                "body": "The first workspace name is stored as part of the bootstrap record and shown throughout the platform.",
                "action": "Set a workspace name in configure mode and save it before completing setup.",
            }
        )
    if not state.get("notification_from_email"):
        guidance.append(
            {
                "key": "notification_from_email_missing",
                "category": "setup",
                "title": "Set a notification sender address",
                "body": "Platform emails and system notifications need a default from-address before the instance can unlock.",
                "action": "Provide a valid notification email address in configure mode, then save the configuration.",
            }
        )
    if not state.get("auth_mode"):
        guidance.append(
            {
                "key": "auth_mode_missing",
                "category": "setup",
                "title": "Choose an authentication mode",
                "body": "The instance must record which IAM mode it is using before setup can be completed.",
                "action": "Select built-in IAM in configure mode for this phase, then save the configuration.",
            }
        )
    if not checks.get("jwt_secret_valid", False):
        guidance.append(
            {
                "key": "jwt_secret_valid",
                "category": "runtime",
                "title": "Replace the JWT signing secret",
                "body": "Production sessions remain locked until the control plane is using a strong, non-default JWT secret.",
                "action": "Set JWT_SECRET to a random value with at least 32 characters and restart the control-plane services.",
            }
        )
    if not checks.get("platform_secrets_key_configured", False):
        guidance.append(
            {
                "key": "platform_secrets_key_configured",
                "category": "runtime",
                "title": "Configure the secrets encryption key",
                "body": "Workspace and provider secrets should not be stored until PLATFORM_SECRETS_KEY is configured for encryption at rest.",
                "action": "Generate a Fernet key, set PLATFORM_SECRETS_KEY in the environment, and restart the stack before completing setup.",
            }
        )
    if not checks.get("database_ok", False):
        guidance.append(
            {
                "key": "database_ok",
                "category": "runtime",
                "title": "Restore database connectivity",
                "body": "The control plane could not confirm it can query the primary database from the current runtime.",
                "action": "Check DATABASE_URL, database health, and network reachability, then reload the setup page after the database is healthy.",
            }
        )

    return guidance


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
    return summarize_bootstrap(
        stored=_load_bootstrap_payload(db),
        checks=build_runtime_checks(db),
        provider_state=_load_oidc_provider_state(db),
    )


def _load_oidc_provider_state(db: Session) -> dict[str, Any]:
    provider = db.execute(select(OidcProvider).order_by(OidcProvider.created_at)).scalars().first()
    if provider is None:
        return {"exists": False, "is_enabled": False, "name": None}
    return {
        "exists": True,
        "is_enabled": bool(provider.is_enabled),
        "name": provider.name,
    }


def initialize_instance(
    db: Session,
    *,
    tenant_name: str,
    admin_email: str,
    admin_password: str,
    notification_from_email: str,
    auth_mode: str,
) -> User:
    state = get_bootstrap_state(db)
    if state["admin_created"]:
        raise BootstrapConflictError("bootstrap admin already exists; sign in to resume setup")
    selected_auth_mode = validate_auth_mode_for_state(auth_mode, provider_state=state.get("oidc_provider_state"))
    auth_service.validate_password_strength(admin_password)

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
        password_hash="",
        role=UserRole.admin,
    )
    auth_service.set_password(admin, admin_password, increment_session_version=False)
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
            "auth_mode": selected_auth_mode,
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
    auth_mode: str | None = None,
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
    if auth_mode is not None:
        payload["auth_mode"] = validate_auth_mode_for_state(
            auth_mode,
            provider_state=state.get("oidc_provider_state"),
        )

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


def validate_auth_mode(auth_mode: str | None) -> str:
    value = (auth_mode or "").strip()
    if value not in SUPPORTED_AUTH_MODES:
        supported = ", ".join(SUPPORTED_AUTH_MODES)
        raise BootstrapValidationError(f"unsupported auth_mode {value!r}; supported values: {supported}")
    return value


def validate_auth_mode_for_state(
    auth_mode: str | None,
    *,
    provider_state: Mapping[str, Any] | None,
) -> str:
    value = validate_auth_mode(auth_mode)
    if value in AUTH_MODES_REQUIRING_OIDC_PROVIDER:
        state = provider_state or {}
        if not state.get("exists") or not state.get("is_enabled"):
            raise BootstrapValidationError(
                f"auth_mode {value!r} requires an enabled OIDC provider; configure one under Admin → Authentication first"
            )
    return value


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
