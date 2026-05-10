from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession, require_role
from app.models import User
from app.schemas.secrets import (
    WorkspaceSecretCreate,
    WorkspaceSecretPublic,
    WorkspaceSecretUpdate,
)
from app.models import ConnectionScope
from app.services import installations_service, secrets_service

router = APIRouter(prefix="/admin/secrets", tags=["admin", "secrets"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


@router.get("", response_model=list[WorkspaceSecretPublic])
def list_secrets(actor: AdminOnly, db: DbSession) -> list[WorkspaceSecretPublic]:
    rows = secrets_service.list_workspace_secrets(db, tenant_id=actor.tenant_id)
    return [WorkspaceSecretPublic.model_validate(s) for s in rows]


@router.post("", response_model=WorkspaceSecretPublic, status_code=status.HTTP_201_CREATED)
def create_secret(
    payload: WorkspaceSecretCreate,
    actor: AdminOnly,
    db: DbSession,
) -> WorkspaceSecretPublic:
    existing = secrets_service.get_workspace_secret_by_name(
        db, tenant_id=actor.tenant_id, name=payload.name
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"workspace secret '{payload.name}' already exists; use PUT to rotate",
        )
    secret = secrets_service.upsert_workspace_secret(
        db, tenant_id=actor.tenant_id, name=payload.name, value=payload.value
    )
    installations_service.sync_connection_from_secret(
        db,
        tenant_id=actor.tenant_id,
        key=payload.name,
        scope=ConnectionScope.workspace,
    )
    db.commit()
    return WorkspaceSecretPublic.model_validate(secret)


@router.put("/{secret_id}", response_model=WorkspaceSecretPublic)
def rotate_secret(
    secret_id: uuid.UUID,
    payload: WorkspaceSecretUpdate,
    actor: AdminOnly,
    db: DbSession,
) -> WorkspaceSecretPublic:
    rows = secrets_service.list_workspace_secrets(db, tenant_id=actor.tenant_id)
    target = next((s for s in rows if s.id == secret_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    secret = secrets_service.upsert_workspace_secret(
        db, tenant_id=actor.tenant_id, name=target.name, value=payload.value
    )
    installations_service.sync_connection_from_secret(
        db,
        tenant_id=actor.tenant_id,
        key=target.name,
        scope=ConnectionScope.workspace,
    )
    db.commit()
    return WorkspaceSecretPublic.model_validate(secret)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(secret_id: uuid.UUID, actor: AdminOnly, db: DbSession) -> None:
    rows = secrets_service.list_workspace_secrets(db, tenant_id=actor.tenant_id)
    target = next((secret for secret in rows if secret.id == secret_id), None)
    deleted = secrets_service.delete_workspace_secret(
        db, tenant_id=actor.tenant_id, secret_id=secret_id
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    if target is not None:
        installations_service.mark_connection_pending_without_secret(
            db,
            tenant_id=actor.tenant_id,
            key=target.name,
            scope=ConnectionScope.workspace,
        )
    db.commit()
