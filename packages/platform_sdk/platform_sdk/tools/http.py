"""tools.http.request — generic HTTP egress through the gateway.

The gateway enforces the agent's permissions.http_allowlist. Calls to
URLs not in the allowlist return 403.

    >>> from platform_sdk import tools
    >>> res = tools.http.get("https://api.example.com/things")
    >>> if res.status_code == 200:
    ...     data = res.json()
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

from platform_sdk import _client


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: str
    truncated: bool

    @property
    def text(self) -> str:
        return self.body

    def json(self) -> Any:
        return _json.loads(self.body)


def request(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json: Any | None = None,
    body: str | None = None,
    timeout_seconds: float = 30.0,
) -> HttpResponse:
    payload: dict[str, Any] = {
        "method": method,
        "url": url,
        "timeout_seconds": timeout_seconds,
    }
    if params is not None:
        payload["params"] = params
    if headers is not None:
        payload["headers"] = headers
    if json is not None:
        payload["json"] = json
    if body is not None:
        payload["body"] = body
    res = _client.post("/tools/http/request", payload)
    return HttpResponse(
        status_code=int(res["status_code"]),
        headers=dict(res.get("headers", {})),
        body=str(res.get("body", "")),
        truncated=bool(res.get("truncated", False)),
    )


def get(url: str, **kwargs: Any) -> HttpResponse:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> HttpResponse:
    return request("POST", url, **kwargs)
