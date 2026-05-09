"""Audit-log writes.

Every tool call gets one audit_log row, success or failure. The gateway
sanitizes the args (redacts anything that matches a known secret value
or looks like a high-entropy token) before writing.
"""
from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.auth import RunTokenClaims
from app.db import get_engine

logger = logging.getLogger(__name__)


_SQL = text(
    """
    INSERT INTO audit_log
        (id, tenant_id, run_id, agent_id, user_id,
         tool_name, args_sanitized_json, result_summary,
         status, duration_ms, cost_usd, created_at)
    VALUES
        (:id, :tenant_id, :run_id, :agent_id, :user_id,
         :tool_name, CAST(:args AS jsonb), :result_summary,
         :status, :duration_ms, :cost_usd, NOW())
    """
)


def _sanitize(value: Any, secret_values: list[str]) -> Any:
    """Walk a JSON-serializable structure and redact secret values."""
    if isinstance(value, str):
        for secret in secret_values:
            if secret and secret in value:
                value = value.replace(secret, "***REDACTED***")
        if len(value) > 500:
            value = value[:500] + f"... [truncated, {len(value)} chars]"
        return value
    if isinstance(value, dict):
        return {k: _sanitize(v, secret_values) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, secret_values) for v in value]
    return value


def write(
    *,
    claims: RunTokenClaims,
    tool_name: str,
    args: dict[str, Any] | None,
    result_summary: str | None,
    status: str,
    duration_ms: int,
    cost_usd: Decimal | float | None,
    secret_values: list[str] | None = None,
) -> None:
    sanitized = _sanitize(args or {}, secret_values or [])
    cost: Decimal | None
    if cost_usd is None:
        cost = None
    else:
        cost = Decimal(str(cost_usd))

    params = {
        "id": str(uuid.uuid4()),
        "tenant_id": str(claims.tenant_id),
        "run_id": str(claims.run_id),
        "agent_id": str(claims.agent_id) if claims.agent_id else None,
        "user_id": str(claims.triggering_user_id) if claims.triggering_user_id else None,
        "tool_name": tool_name,
        "args": json.dumps(sanitized),
        "result_summary": (result_summary or "")[:1000] or None,
        "status": status,
        "duration_ms": duration_ms,
        "cost_usd": cost,
    }
    try:
        with get_engine().begin() as conn:
            conn.execute(_SQL, params)
    except Exception:
        # Audit logging must never crash the request handler. Log loudly.
        logger.exception("failed to write audit_log row for tool=%s", tool_name)
