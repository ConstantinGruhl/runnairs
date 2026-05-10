"""Caller-scoped endpoints: secrets the user has connected to themselves."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.secrets import (
    WorkspaceSecretCreate,
    WorkspaceSecretPublic,
    WorkspaceSecretUpdate,
)
from app.services import secrets_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/secrets", response_model=list[WorkspaceSecretPublic])
def list_my_secrets(actor: CurrentUser, db: DbSession) -> list[WorkspaceSecretPublic]:
    rows = secrets_service.list_user_secrets(
        db, tenant_id=actor.tenant_id, user_id=actor.id
    )
    return [WorkspaceSecretPublic.model_validate(s) for s in rows]


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
    db.commit()
    return WorkspaceSecretPublic.model_validate(secret)


@router.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_secret(
    secret_id: uuid.UUID,
    actor: CurrentUser,
    db: DbSession,
) -> None:
    deleted = secrets_service.delete_user_secret(
        db, tenant_id=actor.tenant_id, user_id=actor.id, secret_id=secret_id
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
    db.commit()
