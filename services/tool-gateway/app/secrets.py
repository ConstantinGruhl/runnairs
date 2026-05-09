"""Secret resolution by scope.

For Phase 3 only workspace-scope secrets exist. User-scope resolution
(per triggering user) lands in Phase 8.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.auth import RunTokenClaims, SecretGrant
from app.db import get_engine
from app.secret_store import get_secret_store


class SecretResolutionError(Exception):
    pass


def _has_grant(claims: RunTokenClaims, name: str) -> SecretGrant | None:
    for grant in claims.secret_grants:
        if grant.name == name:
            return grant
    return None


def resolve(claims: RunTokenClaims, name: str) -> str:
    """Resolve a secret value by name using the run's grants and tenant."""
    grant = _has_grant(claims, name)
    if grant is None:
        raise SecretResolutionError(
            f"agent has no grant for secret '{name}'; declare it in agent.yaml"
        )

    if grant.scope == "workspace":
        return _resolve_workspace(claims.tenant_id, name)
    if grant.scope == "user":
        if claims.triggering_user_id is None:
            raise SecretResolutionError(
                f"user-scope secret '{name}' requires a triggering user"
            )
        return _resolve_user(claims.tenant_id, claims.triggering_user_id, name)

    raise SecretResolutionError(f"unknown secret scope: {grant.scope}")


def _resolve_workspace(tenant_id: uuid.UUID, name: str) -> str:
    row = _query_secret(tenant_id=tenant_id, owner_user_id=None, scope="workspace", name=name)
    if row is None:
        raise SecretResolutionError(
            f"workspace secret '{name}' not configured for this tenant"
        )
    return get_secret_store().decrypt(bytes(row))


def _resolve_user(tenant_id: uuid.UUID, user_id: uuid.UUID, name: str) -> str:
    row = _query_secret(tenant_id=tenant_id, owner_user_id=user_id, scope="user", name=name)
    if row is None:
        raise SecretResolutionError(
            f"user-scope secret '{name}' not connected for the triggering user"
        )
    return get_secret_store().decrypt(bytes(row))


def _query_secret(
    *, tenant_id: uuid.UUID, owner_user_id: uuid.UUID | None, scope: str, name: str
) -> bytes | None:
    if owner_user_id is None:
        sql = text(
            "SELECT ciphertext FROM secret "
            "WHERE tenant_id = :t AND scope = :s AND owner_user_id IS NULL AND name = :n"
        )
        params = {"t": str(tenant_id), "s": scope, "n": name}
    else:
        sql = text(
            "SELECT ciphertext FROM secret "
            "WHERE tenant_id = :t AND scope = :s AND owner_user_id = :o AND name = :n"
        )
        params = {"t": str(tenant_id), "s": scope, "n": name, "o": str(owner_user_id)}

    with get_engine().begin() as conn:
        result = conn.execute(sql, params).first()
    if result is None:
        return None
    return result[0]
