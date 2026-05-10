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


def available_workspace_connection_keys(db: Session, *, tenant_id: uuid.UUID) -> set[str]:
    connection_keys = {
        row.key
        for row in db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.workspace,
                Connection.status == ConnectionStatus.ready,
                Connection.user_id.is_(None),
            )
        )
        .scalars()
        .all()
    }
    secret_keys = {
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
    return connection_keys | secret_keys


def available_user_connection_keys(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> set[str]:
    if user_id is None:
        return set()

    connection_keys = {
        row.key
        for row in db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.user,
                Connection.status == ConnectionStatus.ready,
                Connection.user_id == user_id,
            )
        )
        .scalars()
        .all()
    }
    secret_keys = {
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
    return connection_keys | secret_keys


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
    connection_rows = (
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
    by_key = {row.key: row for row in connection_rows}
    state: dict[str, dict[str, Any]] = {}
    for key in descriptor.get("workspace_connections", []):
        state[key] = _connection_payload(by_key.get(key), key=key, scope=ConnectionScope.workspace)
    for key in descriptor.get("user_connections", []):
        state[key] = _connection_payload(by_key.get(key), key=key, scope=ConnectionScope.user)
    return state


def sync_connection_from_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> Connection:
    query = select(Connection).where(
        Connection.tenant_id == tenant_id,
        Connection.key == key,
        Connection.scope == scope,
    )
    if scope == ConnectionScope.workspace:
        query = query.where(Connection.user_id.is_(None))
    else:
        query = query.where(Connection.user_id == user_id)

    connection = db.execute(query).scalar_one_or_none()
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
            secret_refs_json={},
        )
        db.add(connection)
        db.flush()
        return connection

    connection.provider_key = connection.provider_key or infer_provider_key(key)
    connection.status = ConnectionStatus.ready
    connection.display_name = connection.display_name or key
    db.flush()
    return connection


def delete_connection_for_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> None:
    query = select(Connection).where(
        Connection.tenant_id == tenant_id,
        Connection.key == key,
        Connection.scope == scope,
    )
    if scope == ConnectionScope.workspace:
        query = query.where(Connection.user_id.is_(None))
    else:
        query = query.where(Connection.user_id == user_id)
    connection = db.execute(query).scalar_one_or_none()
    if connection is not None:
        db.delete(connection)
        db.flush()


def infer_provider_key(key: str) -> str:
    for provider_key, plugin in PROVIDER_PLUGINS.items():
        if key in plugin["connection_keys"]:
            return provider_key
    return "custom"


def _connection_payload(
    connection: Connection | None,
    *,
    key: str,
    scope: ConnectionScope,
) -> dict[str, Any]:
    if connection is None:
        return {
            "provider_key": infer_provider_key(key),
            "scope": scope.value,
            "status": "missing",
            "display_name": key,
        }
    return {
        "provider_key": connection.provider_key,
        "scope": connection.scope.value,
        "status": connection.status.value,
        "display_name": connection.display_name,
    }
