"""Run-token authentication.

Run tokens are short-lived JWTs minted by the control plane (or a CLI
helper for testing). They carry the run id, tenant, agent, the list of
allowed tools, and the secret grants — i.e. everything the gateway
needs to authorize a tool call without reading the database.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from app.config import settings


@dataclass(frozen=True)
class SecretGrant:
    name: str
    scope: str  # "workspace" | "user"


@dataclass(frozen=True)
class RunTokenClaims:
    run_id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_version_id: uuid.UUID | None
    tenant_id: uuid.UUID
    triggering_user_id: uuid.UUID | None
    allowed_tools: frozenset[str]
    secret_grants: tuple[SecretGrant, ...]
    approvals_required_for: frozenset[str]


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(value)


def _require_uuid(value: str | None, field: str) -> uuid.UUID:
    if value is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"run token missing {field}")
    return uuid.UUID(value)


def parse_run_token(token: str) -> RunTokenClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid run token: {e}") from e

    if payload.get("typ") != "run":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token is not a run token")

    grants_raw = payload.get("secret_grants", [])
    grants: list[SecretGrant] = []
    for g in grants_raw:
        try:
            grants.append(SecretGrant(name=g["name"], scope=g["scope"]))
        except (KeyError, TypeError) as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"malformed secret grant: {e}") from e

    return RunTokenClaims(
        run_id=_require_uuid(payload.get("run_id"), "run_id"),
        agent_id=_parse_uuid(payload.get("agent_id")),
        agent_version_id=_parse_uuid(payload.get("agent_version_id")),
        tenant_id=_require_uuid(payload.get("tenant_id"), "tenant_id"),
        triggering_user_id=_parse_uuid(payload.get("triggering_user_id")),
        allowed_tools=frozenset(payload.get("allowed_tools", [])),
        secret_grants=tuple(grants),
        approvals_required_for=frozenset(payload.get("approvals_required_for", [])),
    )


def require_run_token(
    authorization: Annotated[str | None, Header()] = None,
) -> RunTokenClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    return parse_run_token(token)


RunClaims = Annotated[RunTokenClaims, Depends(require_run_token)]
