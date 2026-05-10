"""Docker-based execution backend.

Runs each agent in a fresh container with the platform's invariants:
- read-only root, tmpfs at /tmp, no privileged, all caps dropped
- network = agent-egress only (the gateway is the sole reachable peer)
- memory and CPU limits from agent.yaml
- wall-time timeout enforced by container.wait(timeout=...)

The worker calls .execute(run_id); this method returns when the run row
is final.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from sqlalchemy import select

from app import run_tokens
from app.core.db import SessionLocal
from app.execution.backend import ExecutionBackend, ExecutionOutcome
from app.models import AgentVersion, AutomationInstallation, Run, RunStatus
from app.services import installations_service
from app.services.package_descriptor import normalize_stored_descriptor

logger = logging.getLogger(__name__)

RESULT_MARKER = "__RESULT__"


class DockerExecutionBackend(ExecutionBackend):
    def __init__(self) -> None:
        self._client = docker.from_env()
        self._egress_network = os.environ.get(
            "AGENT_EGRESS_NETWORK", "agent-platform_agent-egress"
        )
        self._gateway_url = os.environ.get("TOOL_GATEWAY_URL", "http://tool-gateway:8001")

    def execute(self, run_id: uuid.UUID) -> ExecutionOutcome:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"run {run_id} not found")
            version = db.get(AgentVersion, run.agent_version_id)
            if version is None:
                raise RuntimeError(f"agent_version {run.agent_version_id} not found")

            run.status = RunStatus.running
            run.started_at = datetime.now(timezone.utc)
            db.commit()

            tenant_id = _tenant_for_run(db, run)
            manifest = normalize_stored_descriptor(
                version.manifest_json,
                descriptor_format=version.descriptor_format,
            )
            image_tag = version.image_tag
            installation = db.execute(
                select(AutomationInstallation).where(AutomationInstallation.agent_id == run.agent_id)
            ).scalar_one_or_none()
            installation_state = {
                "enabled_modules": installations_service.enabled_modules_for_installation(
                    manifest,
                    installation,
                ),
                "connections": installations_service.build_connection_state(
                    db=db,
                    descriptor=manifest,
                    tenant_id=tenant_id,
                    user_id=run.triggering_user_id,
                ),
                "config": installations_service.installation_config(installation),
            }

        if not image_tag:
            return self._fail(run_id, "agent_version has no image_tag")

        permissions = manifest.get("permissions", {})
        allowed_tools = list(permissions.get("tools", []))
        secret_grants = [
            {"name": s["name"], "scope": s.get("scope", "workspace")}
            for s in permissions.get("secrets", [])
        ]
        approvals_required = list((manifest.get("approvals", {}) or {}).get("required_for", []))
        http_allowlist = list(permissions.get("http_allowlist", []) or [])
        limits = manifest.get("limits", {}) or {}
        timeout_seconds = int(limits.get("timeout_seconds", 300))
        memory_mb = int(limits.get("memory_mb", 512))

        # If the agent declares any approvals, give the container plenty of
        # wall time so it can sit in awaiting_approval without being killed.
        approval_buffer_seconds = 1800 if approvals_required else 0
        container_timeout_seconds = timeout_seconds + approval_buffer_seconds

        token = run_tokens.mint(
            run_id=run_id,
            tenant_id=tenant_id,
            agent_id=run.agent_id,
            agent_version_id=run.agent_version_id,
            triggering_user_id=run.triggering_user_id,
            allowed_tools=allowed_tools,
            secret_grants=secret_grants,
            approvals_required_for=approvals_required,
            http_allowlist=http_allowlist,
            installation_state=installation_state,
            ttl_minutes=max(2, container_timeout_seconds // 60 + 5),
        )

        env = {
            "RUN_ID": str(run_id),
            "RUN_TOKEN": token,
            "TOOL_GATEWAY_URL": self._gateway_url,
            "RUN_INPUTS": json.dumps(run.inputs_json or {}),
            "RUN_INSTALLATION_STATE": json.dumps(installation_state),
        }

        return self._run_container(
            run_id=run_id,
            image_tag=image_tag,
            env=env,
            timeout_seconds=container_timeout_seconds,
            memory_mb=memory_mb,
        )

    def _run_container(
        self,
        *,
        run_id: uuid.UUID,
        image_tag: str,
        env: dict[str, str],
        timeout_seconds: int,
        memory_mb: int,
    ) -> ExecutionOutcome:
        container = None
        started = time.perf_counter()
        try:
            try:
                container = self._client.containers.create(
                    image=image_tag,
                    name=f"agent-run-{run_id}",
                    environment=env,
                    network=self._egress_network,
                    mem_limit=f"{memory_mb}m",
                    nano_cpus=int(1e9),  # 1 CPU
                    read_only=True,
                    tmpfs={"/tmp": "rw,size=64m"},
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    working_dir="/agent",
                    detach=True,
                    labels={
                        "platform.run_id": str(run_id),
                        "platform.kind": "agent-run",
                    },
                )
            except ImageNotFound:
                return self._fail(run_id, f"image {image_tag!r} not found")
            except APIError as e:
                return self._fail(run_id, f"docker API error: {e}")

            container.start()

            try:
                result = container.wait(timeout=timeout_seconds + 5)
                exit_code = int(result.get("StatusCode", -1))
                timed_out = False
            except Exception:
                # docker SDK raises ReadTimeout on timeout. Kill the container.
                try:
                    container.kill()
                except Exception:
                    logger.exception("failed to kill container after timeout")
                exit_code = -1
                timed_out = True

            try:
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            except Exception:
                logs = ""

            duration = time.perf_counter() - started
            return self._finalize(
                run_id=run_id,
                exit_code=exit_code,
                logs=logs,
                duration_seconds=duration,
                timed_out=timed_out,
                timeout_seconds=timeout_seconds,
            )

        except ContainerError as e:
            return self._fail(run_id, f"container error: {e}", exit_code=e.exit_status)
        except NotFound:
            return self._fail(run_id, "container disappeared")
        except Exception as e:  # noqa: BLE001
            logger.exception("unexpected docker error")
            return self._fail(run_id, f"unexpected docker error: {e}")
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    logger.exception("failed to remove container %s", container.id)

    def _finalize(
        self,
        *,
        run_id: uuid.UUID,
        exit_code: int,
        logs: str,
        duration_seconds: float,
        timed_out: bool,
        timeout_seconds: int,
    ) -> ExecutionOutcome:
        result, parse_err = _parse_result(logs)
        stdout_tail = logs[-2000:]

        if timed_out:
            return self._update_run(
                run_id=run_id,
                status="failed",
                error=f"timed out after {timeout_seconds}s",
                result=None,
                exit_code=exit_code,
                stdout_tail=stdout_tail,
                duration_seconds=duration_seconds,
            )

        if exit_code != 0:
            return self._update_run(
                run_id=run_id,
                status="failed",
                error=f"agent exited with code {exit_code}\n{stdout_tail[-500:]}",
                result=None,
                exit_code=exit_code,
                stdout_tail=stdout_tail,
                duration_seconds=duration_seconds,
            )

        if parse_err is not None:
            return self._update_run(
                run_id=run_id,
                status="failed",
                error=f"could not parse result: {parse_err}",
                result=None,
                exit_code=exit_code,
                stdout_tail=stdout_tail,
                duration_seconds=duration_seconds,
            )

        return self._update_run(
            run_id=run_id,
            status="succeeded",
            error=None,
            result=result,
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            duration_seconds=duration_seconds,
        )

    def _fail(self, run_id: uuid.UUID, error: str, *, exit_code: int | None = None) -> ExecutionOutcome:
        return self._update_run(
            run_id=run_id,
            status="failed",
            error=error,
            result=None,
            exit_code=exit_code,
            stdout_tail=None,
            duration_seconds=0.0,
        )

    def _update_run(
        self,
        *,
        run_id: uuid.UUID,
        status: str,
        error: str | None,
        result: dict | None,
        exit_code: int | None,
        stdout_tail: str | None,
        duration_seconds: float,
    ) -> ExecutionOutcome:
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"run {run_id} disappeared mid-execution")
            run.status = RunStatus(status)
            run.error = error
            run.result_json = result
            run.finished_at = datetime.now(timezone.utc)
            db.commit()

        return ExecutionOutcome(
            status=status,
            result=result,
            error=error,
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            duration_seconds=duration_seconds,
        )


def _tenant_for_run(db, run: Run) -> uuid.UUID:
    from app.models import Agent

    agent = db.get(Agent, run.agent_id)
    if agent is None:
        raise RuntimeError(f"agent {run.agent_id} not found for run {run.id}")
    return agent.tenant_id


def _parse_result(logs: str) -> tuple[dict | None, str | None]:
    for line in reversed(logs.splitlines()):
        line = line.rstrip()
        if line.startswith(RESULT_MARKER):
            payload = line[len(RESULT_MARKER):].strip()
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError as e:
                return None, f"invalid JSON after {RESULT_MARKER}: {e}"
            if not isinstance(parsed, dict):
                return None, f"{RESULT_MARKER} payload must be a JSON object"
            return parsed, None
    return None, f"no {RESULT_MARKER} line in agent stdout"
