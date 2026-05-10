"""Run context.

Exposed to agents as `from platform_sdk import ctx`. Carries inputs,
the run id, a small log helper, and request_approval for human
in-the-loop pauses.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

from platform_sdk._client import GatewayError, post


@dataclass(frozen=True)
class Approval:
    approved: bool
    status: str  # "approved" | "denied" | "timeout"
    decided_by: str | None
    decided_at: str | None


class _Context:
    @property
    def run_id(self) -> uuid.UUID:
        rid = os.environ.get("RUN_ID")
        if not rid:
            raise RuntimeError("RUN_ID is not set; the agent runtime must inject it")
        return uuid.UUID(rid)

    @property
    def inputs(self) -> dict[str, Any]:
        raw = os.environ.get("RUN_INPUTS", "{}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"RUN_INPUTS is not valid JSON: {e}") from e
        if not isinstance(value, dict):
            raise RuntimeError("RUN_INPUTS must be a JSON object")
        return value

    def log(self, message: str, level: str = "info") -> None:
        """Emit a structured-ish log line. Captured by the worker."""
        sys.stdout.write(f"[agent:{level}] {message}\n")
        sys.stdout.flush()

    def request_approval(
        self,
        *,
        action: str,
        title: str,
        body: str | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 1800,
    ) -> Approval:
        """Pause the run until a human approves or denies the named action.

        The action string should match the tool the approval gates (e.g.
        "email.send"). After approval, that tool can be called and the
        gateway will accept it.
        """
        created = post(
            "/approvals",
            {
                "action": action,
                "title": title,
                "body": body,
                "payload": payload,
            },
        )
        approval_id = created["approval_id"]
        self.log(f"awaiting approval for {action!r} (id={approval_id})", level="info")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                result = post(
                    f"/approvals/{approval_id}/wait",
                    {},
                    timeout=90.0,
                )
            except GatewayError:
                # Transient error — back off and retry until the deadline.
                time.sleep(2)
                continue

            status = result.get("status", "pending")
            if status != "pending":
                return Approval(
                    approved=(status == "approved"),
                    status=status,
                    decided_by=result.get("decided_by"),
                    decided_at=result.get("decided_at"),
                )

        self.log(f"approval timed out after {timeout_seconds}s", level="warn")
        return Approval(approved=False, status="timeout", decided_by=None, decided_at=None)


ctx = _Context()
