"""Per-call policy checks against the run token's claims.

Phase 3 just ensures the tool is in the allowed list. Phase 7 adds
approval checks; Phase 8 adds the HTTP allowlist.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.auth import RunTokenClaims


def ensure_tool_allowed(claims: RunTokenClaims, tool_name: str) -> None:
    if tool_name not in claims.allowed_tools:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"tool '{tool_name}' is not in the agent's permissions.tools",
        )
