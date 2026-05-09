"""Run context.

Exposed to agents as `from platform_sdk import ctx`. Carries inputs,
the run id, and a small log helper. ctx.request_approval lands in
Phase 7.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any


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


ctx = _Context()
