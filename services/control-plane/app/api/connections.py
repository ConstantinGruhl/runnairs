from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Connection, ConnectionScope, ConnectionStatus, User
from app.services import installations_service, secrets_service

router = APIRouter(prefix="/admin", tags=["connections"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


class WorkspaceConnectionCreate(BaseModel):
    key: str
    provider_key: str | None = None
    display_name: str | None = None
    scopes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    secret_value: str | None = None


@router.get("/connections")
def list_workspace_connections(actor: AdminOnly, db: DbSession) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(Connection).where(
                Connection.tenant_id == actor.tenant_id,
                Connection.user_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(row.id),
            "key": row.key,
            "provider_key": row.provider_key,
            "scope": row.scope.value,
            "status": row.status.value,
            "display_name": row.display_name,
            "scopes": row.scopes_json,
        }
        for row in rows
    ]


@router.post("/connections")
def create_workspace_connection(
    payload: WorkspaceConnectionCreate,
    actor: AdminOnly,
    db: DbSession,
) -> dict[str, Any]:
    connection = db.execute(
        select(Connection).where(
            Connection.tenant_id == actor.tenant_id,
            Connection.user_id.is_(None),
            Connection.key == payload.key,
            Connection.scope == ConnectionScope.workspace,
        )
    ).scalar_one_or_none()
    if connection is None:
        connection = Connection(
            tenant_id=actor.tenant_id,
            user_id=None,
            key=payload.key,
            provider_key=payload.provider_key or installations_service.infer_provider_key(payload.key),
            scope=ConnectionScope.workspace,
            status=ConnectionStatus.ready,
            display_name=payload.display_name or payload.key,
            scopes_json=list(payload.scopes),
            config_json=dict(payload.config),
            secret_refs_json=dict(payload.secret_refs),
        )
        db.add(connection)
    else:
        connection.provider_key = payload.provider_key or connection.provider_key
        connection.status = ConnectionStatus.ready
        connection.display_name = payload.display_name or connection.display_name
        connection.scopes_json = list(payload.scopes)
        connection.config_json = dict(payload.config)
        connection.secret_refs_json = dict(payload.secret_refs)

    if payload.secret_value:
        secrets_service.upsert_workspace_secret(
            db,
            tenant_id=actor.tenant_id,
            name=payload.key,
            value=payload.secret_value,
        )

    db.commit()
    db.refresh(connection)
    return {
        "id": str(connection.id),
        "key": connection.key,
        "provider_key": connection.provider_key,
        "scope": connection.scope.value,
        "status": connection.status.value,
        "display_name": connection.display_name,
        "scopes": connection.scopes_json,
    }
