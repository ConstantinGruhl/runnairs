"""Execution backend interface.

A backend is responsible for taking a queued Run row and producing a
finished one — running the agent in isolation, collecting its output,
and updating the row. Today we ship `DockerExecutionBackend`; a future
`KubernetesExecutionBackend` would be a drop-in.

The backend is the *only* place that knows about Docker, K8s, etc. The
worker just calls `execute(run_id)`.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionOutcome:
    status: str  # "succeeded" | "failed"
    result: dict[str, Any] | None
    error: str | None
    exit_code: int | None
    stdout_tail: str | None
    duration_seconds: float


class ExecutionBackend(ABC):
    @abstractmethod
    def execute(self, run_id: uuid.UUID) -> ExecutionOutcome:
        """Run the agent end-to-end and update the run row.

        Implementations must:
          - Update run.started_at / status=running before launch.
          - Inject RUN_TOKEN, RUN_ID, TOOL_GATEWAY_URL into the agent.
          - Enforce the manifest's limits (mem, cpu, timeout).
          - Confine egress to the gateway only.
          - Capture stdout, parse the agent's `__RESULT__ {...}` line.
          - Update run.status / finished_at / result_json / error.
        """
