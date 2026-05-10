"""tools.http.request — generic HTTP egress, gated by per-agent allowlist.

Patterns are simple shell-style globs against the full URL, e.g.
    https://api.hubspot.com/*
    https://*.atlassian.net/*
"""
from __future__ import annotations

import logging
import re
import time
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app import audit
from app.auth import RunClaims
from app.policy import ensure_tool_allowed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools/http", tags=["http"])

TOOL_NAME = "http.request"
_MAX_BYTES = 1_000_000  # 1 MB response cap


class HttpRequest(BaseModel):
    method: str = Field(default="GET")
    url: str
    params: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    json_body: Any | None = Field(default=None, alias="json")
    body: str | None = None
    timeout_seconds: float = 30.0

    class Config:
        populate_by_name = True


class HttpResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str
    truncated: bool


@router.post("/request", response_model=HttpResponse)
def http_request(payload: HttpRequest, claims: RunClaims) -> HttpResponse:
    ensure_tool_allowed(claims, TOOL_NAME)
    _ensure_url_allowed(claims.http_allowlist, payload.url)

    start = time.perf_counter()
    error: Exception | None = None
    response: httpx.Response | None = None
    try:
        with httpx.Client(timeout=payload.timeout_seconds) as client:
            response = client.request(
                payload.method.upper(),
                payload.url,
                params=payload.params,
                headers=payload.headers,
                json=payload.json_body,
                content=payload.body,
            )
    except Exception as e:  # noqa: BLE001
        error = e

    duration_ms = int((time.perf_counter() - start) * 1000)
    audit_args = {
        "method": payload.method.upper(),
        "url": payload.url,
        "header_count": len(payload.headers or {}),
        "param_count": len(payload.params or {}),
    }
    if error is not None or response is None:
        audit.write(
            claims=claims,
            tool_name=TOOL_NAME,
            args=audit_args,
            result_summary=f"error: {error}",
            status="error",
            duration_ms=duration_ms,
            cost_usd=Decimal("0"),
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"http call failed: {error}")

    body_bytes = response.content[:_MAX_BYTES]
    truncated = len(response.content) > _MAX_BYTES
    body_text = body_bytes.decode("utf-8", errors="replace")

    audit.write(
        claims=claims,
        tool_name=TOOL_NAME,
        args=audit_args,
        result_summary=f"{response.status_code} ({len(response.content)} bytes)",
        status="ok" if response.status_code < 400 else "upstream_error",
        duration_ms=duration_ms,
        cost_usd=Decimal("0"),
    )
    return HttpResponse(
        status_code=response.status_code,
        headers=dict(response.headers),
        body=body_text,
        truncated=truncated,
    )


def _ensure_url_allowed(allowlist: frozenset[str], url: str) -> None:
    if not allowlist:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "http.request requires permissions.http_allowlist; none declared",
        )
    for pattern in allowlist:
        if _pattern_to_regex(pattern).match(url):
            return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        f"url {url!r} not in agent's http_allowlist",
    )


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    parts = pattern.split("*")
    return re.compile("^" + ".*".join(re.escape(p) for p in parts) + "$")
