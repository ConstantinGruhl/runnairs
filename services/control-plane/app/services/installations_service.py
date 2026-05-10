from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AutomationInstallation,
    Connection,
    ConnectionScope,
    ConnectionStatus,
    Secret,
    SecretScope,
)
from app.services.provider_registry import PROVIDER_PLUGINS


@dataclass(frozen=True)
class InstallationReadiness:
    ready: bool
    missing_workspace_connections: list[str]
    missing_user_connections: list[str]
    disabled_required_modules: list[str]


def compute_installation_readiness(
    *,
    descriptor: dict[str, Any],
    available_workspace_connections: set[str],
    available_user_connections: set[str],
    enabled_modules: set[str],
) -> InstallationReadiness:
    required_modules = {
        module["id"]
        for module in descriptor.get("modules", [])
        if isinstance(module, dict) and module.get("required")
    }
    disabled_required = sorted(required_modules - enabled_modules)
    missing_workspace = sorted(
        set(descriptor.get("workspace_connections", [])) - available_workspace_connections
    )
    missing_user = sorted(
        set(descriptor.get("user_connections", [])) - available_user_connections
    )
    return InstallationReadiness(
        ready=not missing_workspace and not missing_user and not disabled_required,
        missing_workspace_connections=missing_workspace,
        missing_user_connections=missing_user,
        disabled_required_modules=disabled_required,
    )


def default_enabled_modules(descriptor: dict[str, Any]) -> list[str]:
    return sorted(
        {
            module["id"]
            for module in descriptor.get("modules", [])
            if isinstance(module, dict)
            and module.get("id")
            and (module.get("enabled_by_default") or module.get("required"))
        }
    )


def enabled_modules_for_installation(
    descriptor: dict[str, Any],
    installation: AutomationInstallation | None,
) -> list[str]:
    if installation is None:
        return default_enabled_modules(descriptor)
    if installation.enabled_modules_json is None:
        return default_enabled_modules(descriptor)
    return sorted({module_id for module_id in installation.enabled_modules_json if module_id})


def installation_config(
    installation: AutomationInstallation | None,
) -> dict[str, Any]:
    return dict((installation.config_json or {}) if installation is not None else {})


def workspace_secret_keys(db: Session, *, tenant_id: uuid.UUID) -> set[str]:
    return {
        row.name
        for row in db.execute(
            select(Secret).where(
                Secret.tenant_id == tenant_id,
                Secret.scope == SecretScope.workspace,
                Secret.owner_user_id.is_(None),
            )
        )
        .scalars()
        .all()
    }


def user_secret_keys(db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> set[str]:
    if user_id is None:
        return set()
    return {
        row.name
        for row in db.execute(
            select(Secret).where(
                Secret.tenant_id == tenant_id,
                Secret.scope == SecretScope.user,
                Secret.owner_user_id == user_id,
            )
        )
        .scalars()
        .all()
    }


def _connection_has_backing_secret(connection: Connection, secret_keys: set[str]) -> bool:
    if connection.key in secret_keys:
        return True
    return any(secret_name in secret_keys for secret_name in connection.secret_refs_json.values())


def available_workspace_connection_keys(db: Session, *, tenant_id: uuid.UUID) -> set[str]:
    secret_keys = workspace_secret_keys(db, tenant_id=tenant_id)
    rows = (
        db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.workspace,
                Connection.user_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    connection_keys = {
        row.key
        for row in rows
        if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, secret_keys)
    }
    legacy_secret_only_keys = secret_keys - {
        row.key
        for row in rows
    }
    return connection_keys | legacy_secret_only_keys


def available_user_connection_keys(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> set[str]:
    secret_keys = user_secret_keys(db, tenant_id=tenant_id, user_id=user_id)
    if user_id is None:
        return set()

    rows = (
        db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.user,
                Connection.user_id == user_id,
            )
        )
        .scalars()
        .all()
    )
    connection_keys = {
        row.key
        for row in rows
        if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, secret_keys)
    }
    legacy_secret_only_keys = secret_keys - {
        row.key
        for row in rows
    }
    return connection_keys | legacy_secret_only_keys


def build_installation_summary(
    *,
    descriptor: dict[str, Any],
    installation: AutomationInstallation | None,
    available_workspace_connections: set[str],
    available_user_connections: set[str],
) -> dict[str, Any]:
    enabled_modules = enabled_modules_for_installation(descriptor, installation)
    readiness = compute_installation_readiness(
        descriptor=descriptor,
        available_workspace_connections=available_workspace_connections,
        available_user_connections=available_user_connections,
        enabled_modules=set(enabled_modules),
    )
    return {
        "status": installation_status(
            installation=installation,
            readiness=readiness,
            enabled_modules=enabled_modules,
        ),
        "ready": readiness.ready,
        "enabled_modules": enabled_modules,
        "missing_workspace_connections": readiness.missing_workspace_connections,
        "missing_user_connections": readiness.missing_user_connections,
        "disabled_required_modules": readiness.disabled_required_modules,
        "config": installation_config(installation),
    }


def installation_status(
    *,
    installation: AutomationInstallation | None,
    readiness: InstallationReadiness,
    enabled_modules: list[str],
) -> str:
    if installation is not None and installation.status:
        current = installation.status.value
        if current == "active":
            return current

    if readiness.disabled_required_modules or readiness.missing_workspace_connections:
        return "blocked"
    if not enabled_modules:
        return "draft"
    return "ready"


def build_connection_state(
    *,
    db: Session,
    descriptor: dict[str, Any],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> dict[str, dict[str, Any]]:
    workspace_secret_names = workspace_secret_keys(db, tenant_id=tenant_id)
    user_secret_names = user_secret_keys(db, tenant_id=tenant_id, user_id=user_id)
    rows = (
        db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                (
                    ((Connection.scope == ConnectionScope.workspace) & Connection.user_id.is_(None))
                    | ((Connection.scope == ConnectionScope.user) & (Connection.user_id == user_id))
                ),
            )
        )
        .scalars()
        .all()
    )
    by_key = {row.key: row for row in rows}
    state: dict[str, dict[str, Any]] = {}
    for key in descriptor.get("workspace_connections", []):
        row = by_key.get(key)
        if row is None and key in workspace_secret_names:
            state[key] = {
                "provider_key": infer_provider_key(key),
                "scope": "workspace",
                "status": "ready",
                "display_name": key,
            }
        elif row is None:
            state[key] = {
                "provider_key": infer_provider_key(key),
                "scope": "workspace",
                "status": "missing",
                "display_name": key,
            }
        else:
            status = (
                "ready"
                if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, workspace_secret_names)
                else "pending"
            )
            state[key] = {
                "provider_key": row.provider_key,
                "scope": row.scope.value,
                "status": status,
                "display_name": row.display_name,
            }
    for key in descriptor.get("user_connections", []):
        row = by_key.get(key)
        if row is None and key in user_secret_names:
            state[key] = {
                "provider_key": infer_provider_key(key),
                "scope": "user",
                "status": "ready",
                "display_name": key,
            }
        elif row is None:
            state[key] = {
                "provider_key": infer_provider_key(key),
                "scope": "user",
                "status": "missing",
                "display_name": key,
            }
        else:
            status = (
                "ready"
                if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, user_secret_names)
                else "pending"
            )
            state[key] = {
                "provider_key": row.provider_key,
                "scope": row.scope.value,
                "status": status,
                "display_name": row.display_name,
            }
    return state


def _connection_by_key(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> Connection | None:
    query = select(Connection).where(
        Connection.tenant_id == tenant_id,
        Connection.key == key,
        Connection.scope == scope,
    )
    if scope == ConnectionScope.workspace:
        query = query.where(Connection.user_id.is_(None))
    else:
        query = query.where(Connection.user_id == user_id)
    return db.execute(query).scalar_one_or_none()


def sync_connection_from_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> Connection:
    connection = _connection_by_key(
        db,
        tenant_id=tenant_id,
        key=key,
        scope=scope,
        user_id=user_id,
    )
    if connection is None:
        connection = Connection(
            tenant_id=tenant_id,
            user_id=user_id if scope == ConnectionScope.user else None,
            key=key,
            provider_key=infer_provider_key(key),
            scope=scope,
            status=ConnectionStatus.ready,
            display_name=key,
            scopes_json=[],
            config_json={},
            secret_refs_json={"primary": key},
        )
        db.add(connection)
        db.flush()
        return connection

    connection.status = ConnectionStatus.ready
    connection.provider_key = connection.provider_key or infer_provider_key(key)
    connection.display_name = connection.display_name or key
    if not connection.secret_refs_json:
        connection.secret_refs_json = {"primary": key}
    db.flush()
    return connection


def mark_connection_pending_without_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> None:
    connection = _connection_by_key(
        db,
        tenant_id=tenant_id,
        key=key,
        scope=scope,
        user_id=user_id,
    )
    if connection is not None:
        connection.status = ConnectionStatus.pending
        db.flush()


def infer_provider_key(key: str) -> str:
    for provider_key, plugin in PROVIDER_PLUGINS.items():
        if key in plugin["connection_keys"]:
            return provider_key
    return "custom"


