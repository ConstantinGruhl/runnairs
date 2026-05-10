"""Caller-scoped endpoints: secrets the user has connected to themselves."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.models import Connection, ConnectionScope
from app.schemas.secrets import (
    WorkspaceSecretCreate,
    WorkspaceSecretPublic,
    WorkspaceSecretUpdate,
)
from app.services import installations_service, secrets_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/secrets", response_model=list[WorkspaceSecretPublic])
def list_my_secrets(actor: CurrentUser, db: DbSession) -> list[WorkspaceSecretPublic]:
    rows = secrets_service.list_user_secrets(
        db, tenant_id=actor.tenant_id, user_id=actor.id
    )
    return [WorkspaceSecretPublic.model_validate(s) for s in rows]


@router.get("/connections")
def list_my_connections(actor: CurrentUser, db: DbSession) -> list[dict]:
    rows = (
        db.execute(
            select(Connection).where(
                Connection.tenant_id == actor.tenant_id,
                Connection.scope == ConnectionScope.user,
                Connection.user_id == actor.id,
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
        }
        for row in rows
    ]


@router.post("/secrets", response_model=WorkspaceSecretPublic, status_code=status.HTTP_201_CREATED)
def connect_secret(
    payload: WorkspaceSecretCreate,
    actor: CurrentUser,
    db: DbSession,
) -> WorkspaceSecretPublic:
    """Connect (or rotate) a user-scope secret like MAILBOX_TOKEN."""
    secret = secrets_service.upsert_user_secret(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        name=payload.name,
        value=payload.value,
    )
    installations_service.sync_connection_from_secret(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        key=payload.name,
        scope=ConnectionScope.user,
    )
    db.commit()
    return WorkspaceSecretPublic.model_validate(secret)


@router.put("/secrets/{secret_id}", response_model=WorkspaceSecretPublic)
def rotate_secret(
    secret_id: uuid.UUID,
    payload: WorkspaceSecretUpdate,
    actor: CurrentUser,
    db: DbSession,
) -> WorkspaceSecretPublic:
    rows = secrets_service.list_user_secrets(
        db, tenant_id=actor.tenant_id, user_id=actor.id
    )
    target = next((s for s in rows if s.id == secret_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    secret = secrets_service.upsert_user_secret(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        name=target.name,
        value=payload.value,
    )
    installations_service.sync_connection_from_secret(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        key=target.name,
        scope=ConnectionScope.user,
    )
    db.commit()
    return WorkspaceSecretPublic.model_validate(secret)


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_secret(
    secret_id: uuid.UUID,
    actor: CurrentUser,
    db: DbSession,
) -> None:
    rows = secrets_service.list_user_secrets(
        db, tenant_id=actor.tenant_id, user_id=actor.id
    )
    target = next((s for s in rows if s.id == secret_id), None)
    deleted = secrets_service.delete_user_secret(
        db, tenant_id=actor.tenant_id, user_id=actor.id, secret_id=secret_id
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    if target is not None:
        installations_service.mark_connection_pending_without_secret(
            db,
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            key=target.name,
            scope=ConnectionScope.user,
        )
    db.commit()
