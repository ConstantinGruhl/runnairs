"""Tiny httpx wrapper for the control plane."""
from __future__ import annotations

from typing import Any

import httpx


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"control plane returned {status}: {detail}")
        self.status = status
        self.detail = detail


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ApiError(resp.status_code, detail)


def post_json(api_url: str, path: str, *, body: dict, token: str | None = None, timeout: float = 30.0) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.post(f"{api_url.rstrip('/')}{path}", json=body, headers=headers, timeout=timeout)
    _raise_for(resp)
    return resp.json()


def post_multipart(
    api_url: str,
    path: str,
    *,
    files: dict[str, tuple[str, bytes, str]],
    data: dict[str, str] | None = None,
    token: str,
    timeout: float = 300.0,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.post(
        f"{api_url.rstrip('/')}{path}",
        files=files,
        data=data,
        headers=headers,
        timeout=timeout,
    )
    _raise_for(resp)
    return resp.json()


def get_json(api_url: str, path: str, *, token: str, timeout: float = 30.0) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{api_url.rstrip('/')}{path}", headers=headers, timeout=timeout)
    _raise_for(resp)
    return resp.json()
