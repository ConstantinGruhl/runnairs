"""Test harness for agent code.

`MockGateway` patches `platform_sdk._client.post` so the agent's
calls into the gateway return canned responses. Use it inside a
`with` block; it auto-restores on exit.

    from platform_sdk.testing import MockGateway

    def test_happy_path():
        with MockGateway() as gw:
            gw.set_inputs({"region": "EMEA"})
            gw.stub_llm_complete(text="hi")
            from main import run
            result = run()
        assert result["text"] == "hi"
        assert gw.calls_to("/tools/llm/complete") == 1
"""
from __future__ import annotations

import json
import os
import uuid
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from platform_sdk import _client


@dataclass
class _Call:
    path: str
    payload: dict[str, Any]


@dataclass
class MockGateway:
    """In-process stand-in for the tool gateway.

    Each `stub_*` method enqueues a response for the next matching call.
    When the queue for a path is empty, the default response (set with
    `default_response_for`) is returned, or RuntimeError is raised.
    """

    calls: list[_Call] = field(default_factory=list)
    _stubs: dict[str, deque] = field(default_factory=dict)
    _defaults: dict[str, Any] = field(default_factory=dict)
    _approval_id_counter: int = 0
    _restore: list[Callable[[], None]] = field(default_factory=list)
    _saved_env: dict[str, str | None] = field(default_factory=dict)

    # ---- lifecycle ----

    def __enter__(self) -> "MockGateway":
        # Inject the env vars the SDK requires.
        for key, value in {
            "RUN_ID": str(uuid.uuid4()),
            "RUN_TOKEN": "test-token",
            "TOOL_GATEWAY_URL": "http://test-gateway",
            "RUN_INPUTS": "{}",
        }.items():
            self._saved_env[key] = os.environ.get(key)
            os.environ[key] = value

        original = _client.post

        def fake_post(path: str, payload: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
            self.calls.append(_Call(path=path, payload=dict(payload)))
            queue = self._stubs.get(path)
            if queue:
                return queue.popleft()
            if path in self._defaults:
                return self._defaults[path]
            raise RuntimeError(
                f"MockGateway: no stub for {path!r}; "
                f"call .stub_*() or .default_response_for() before invoking the agent"
            )

        _client.post = fake_post  # type: ignore[assignment]
        self._restore.append(lambda: setattr(_client, "post", original))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for fn in reversed(self._restore):
            fn()
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ---- input setup ----

    def set_inputs(self, inputs: dict[str, Any]) -> None:
        os.environ["RUN_INPUTS"] = json.dumps(inputs)

    # ---- low-level stubs ----

    def stub(self, path: str, response: dict[str, Any]) -> None:
        self._stubs.setdefault(path, deque()).append(response)

    def default_response_for(self, path: str, response: dict[str, Any]) -> None:
        self._defaults[path] = response

    # ---- ergonomic stubs per tool ----

    def stub_llm_complete(
        self,
        *,
        text: str = "stubbed completion",
        model: str = "gpt-4o-mini",
        tokens_used: int = 10,
        cost_usd: float = 0.0,
        backend: str = "stub",
    ) -> None:
        self.stub(
            "/tools/llm/complete",
            {
                "text": text,
                "model": model,
                "tokens_used": tokens_used,
                "cost_usd": cost_usd,
                "backend": backend,
            },
        )

    def stub_email_send(self, *, ok: bool = True, backend: str = "smtp") -> None:
        self.stub("/tools/email/send", {"ok": ok, "backend": backend})

    def stub_postgres_query(
        self, rows: list[dict[str, Any]], *, columns: list[str] | None = None
    ) -> None:
        self.stub(
            "/tools/postgres/query",
            {
                "rows": list(rows),
                "columns": columns or (list(rows[0].keys()) if rows else []),
                "row_count": len(rows),
            },
        )

    def stub_http_request(
        self,
        *,
        status_code: int = 200,
        body: str = "{}",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.stub(
            "/tools/http/request",
            {
                "status_code": status_code,
                "headers": headers or {},
                "body": body,
                "truncated": False,
            },
        )

    def stub_inbox_list(self, emails: list[dict[str, Any]]) -> None:
        self.stub("/tools/inbox/list", {"emails": list(emails)})

    def stub_approval(
        self,
        *,
        approved: bool = True,
        decided_by: str | None = None,
        decided_at: str | None = "2026-05-10T00:00:00Z",
    ) -> None:
        """Make the next ctx.request_approval(...) return immediately."""
        self._approval_id_counter += 1
        approval_id = f"appr-{self._approval_id_counter}"
        self.stub("/approvals", {"approval_id": approval_id, "status": "pending"})
        # The wait endpoint is path-templated by approval_id; route on prefix.
        self.stub(
            f"/approvals/{approval_id}/wait",
            {
                "status": "approved" if approved else "denied",
                "decided_by": decided_by,
                "decided_at": decided_at,
            },
        )

    # ---- assertions ----

    def calls_to(self, path: str) -> int:
        return sum(1 for c in self.calls if c.path == path)

    def last_call(self, path: str) -> _Call:
        for c in reversed(self.calls):
            if c.path == path:
                return c
        raise AssertionError(f"no call to {path!r}; recorded paths: {[c.path for c in self.calls]}")
