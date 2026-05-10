"""Business logic for tenant-scoped secrets.

For Phase 2 the API only handles workspace secrets. User-scope writes
are accepted by the model but the admin endpoints don't expose them yet.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Secret, SecretScope
from app.services.secret_store import get_secret_store


def list_workspace_secrets(db: Session, *, tenant_id: uuid.UUID) -> Sequence[Secret]:
    return (
        db.execute(
            select(Secret)
            .where(Secret.tenant_id == tenant_id, Secret.scope == SecretScope.workspace)
            .order_by(Secret.name)
        )
        .scalars()
        .all()
    )


def get_workspace_secret_by_name(db: Session, *, tenant_id: uuid.UUID, name: str) -> Secret | None:
    return db.execute(
        select(Secret).where(
            Secret.tenant_id == tenant_id,
            Secret.scope == SecretScope.workspace,
            Secret.owner_user_id.is_(None),
            Secret.name == name,
        )
    ).scalar_one_or_none()


def upsert_workspace_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    name: str,
    value: str,
) -> Secret:
    store = get_secret_store()
    ciphertext = store.encrypt(value)

    existing = get_workspace_secret_by_name(db, tenant_id=tenant_id, name=name)
    if existing is not None:
        existing.ciphertext = ciphertext
        db.flush()
        return existing

    secret = Secret(
        tenant_id=tenant_id,
        scope=SecretScope.workspace,
        owner_user_id=None,
        name=name,
        ciphertext=ciphertext,
    )
    db.add(secret)
    db.flush()
    return secret


def delete_workspace_secret(db: Session, *, tenant_id: uuid.UUID, secret_id: uuid.UUID) -> bool:
    secret = db.get(Secret, secret_id)
    if (
        secret is None
        or secret.tenant_id != tenant_id
        or secret.scope != SecretScope.workspace
    ):
        return False
    db.delete(secret)
    db.flush()
    return True


def reveal_workspace_secret(db: Session, *, tenant_id: uuid.UUID, secret_id: uuid.UUID) -> str | None:
    """Decrypt a workspace secret. Used only for verification flows."""
    secret = db.get(Secret, secret_id)
    if (
        secret is None
        or secret.tenant_id != tenant_id
        or secret.scope != SecretScope.workspace
    ):
        return None
    return get_secret_store().decrypt(secret.ciphertext)


# ---------- user-scope ----------

def list_user_secrets(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Sequence[Secret]:
    return (
        db.execute(
            select(Secret)
            .where(
                Secret.tenant_id == tenant_id,
                Secret.scope == SecretScope.user,
                Secret.owner_user_id == user_id,
            )
            .order_by(Secret.name)
        )
        .scalars()
        .all()
    )


def upsert_user_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    value: str,
) -> Secret:
    store = get_secret_store()
    ciphertext = store.encrypt(value)

    existing = db.execute(
        select(Secret).where(
            Secret.tenant_id == tenant_id,
            Secret.scope == SecretScope.user,
            Secret.owner_user_id == user_id,
            Secret.name == name,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.ciphertext = ciphertext
        db.flush()
        return existing

    secret = Secret(
        tenant_id=tenant_id,
        scope=SecretScope.user,
        owner_user_id=user_id,
        name=name,
        ciphertext=ciphertext,
    )
    db.add(secret)
    db.flush()
    return secret


def delete_user_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    secret_id: uuid.UUID,
) -> bool:
    secret = db.get(Secret, secret_id)
    if (
        secret is None
        or secret.tenant_id != tenant_id
        or secret.scope != SecretScope.user
        or secret.owner_user_id != user_id
    ):
        return False
    db.delete(secret)
    db.flush()
    return True
