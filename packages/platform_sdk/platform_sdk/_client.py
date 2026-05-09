from __future__ import annotations

import os
from typing import Any

import httpx


class GatewayError(Exception):
    """Raised when the tool gateway returns an error or is unreachable."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"tool gateway error ({status}): {detail}")
        self.status = status
        self.detail = detail


def _gateway_url() -> str:
    url = os.environ.get("TOOL_GATEWAY_URL")
    if not url:
        raise RuntimeError(
            "TOOL_GATEWAY_URL is not set; the agent runtime must inject it"
        )
    return url.rstrip("/")


def _run_token() -> str:
    token = os.environ.get("RUN_TOKEN")
    if not token:
        raise RuntimeError(
            "RUN_TOKEN is not set; the agent runtime must inject it"
        )
    return token


def post(path: str, payload: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
    url = f"{_gateway_url()}{path}"
    headers = {"Authorization": f"Bearer {_run_token()}"}
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise GatewayError(0, f"transport error: {e}") from e

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise GatewayError(resp.status_code, detail)
    return resp.json()
