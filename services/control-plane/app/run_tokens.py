"""Run-token minting.

Run tokens are short-lived JWTs scoped to a single agent run. They
contain everything the tool gateway needs to authorize tool calls
without consulting the control plane database.

Used by:
- Phase 3: the cli helper, for testing the SDK <-> gateway path.
- Phase 4+: the run lifecycle, when starting an agent container.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt

from app.core.config import settings


def mint(
    *,
    run_id: uuid.UUID,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None = None,
    agent_version_id: uuid.UUID | None = None,
    triggering_user_id: uuid.UUID | None = None,
    allowed_tools: list[str],
    secret_grants: list[dict[str, str]] | None = None,
    approvals_required_for: list[str] | None = None,
    http_allowlist: list[str] | None = None,
    installation_state: dict[str, Any] | None = None,
    ttl_minutes: int = 30,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "typ": "run",
        "run_id": str(run_id),
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id) if agent_id else None,
        "agent_version_id": str(agent_version_id) if agent_version_id else None,
        "triggering_user_id": str(triggering_user_id) if triggering_user_id else None,
        "allowed_tools": list(allowed_tools),
        "secret_grants": list(secret_grants or []),
        "approvals_required_for": list(approvals_required_for or []),
        "http_allowlist": list(http_allowlist or []),
        "installation_state": installation_state or {},
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
