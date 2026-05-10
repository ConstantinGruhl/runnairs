from __future__ import annotations

import json
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound


INSPECTION_TIMEOUT_SECONDS = 15


class InspectionError(Exception):
    """Raised when inspection cannot complete safely or returns invalid data."""


def inspect_image_package(*, image_tag: str, entrypoint: str) -> dict[str, Any]:
    try:
        client = docker.from_env()
    except DockerException as exc:
        raise InspectionError(f"cannot reach docker daemon for inspection: {exc}") from exc

    container = None
    try:
        container = client.containers.create(
            image=image_tag,
            entrypoint=["python", "-m", "platform_sdk.inspect", "/agent", entrypoint],
            network_disabled=True,
            read_only=True,
            tmpfs={"/tmp": "rw,size=16m"},
            mem_limit="128m",
            nano_cpus=int(0.5e9),
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            working_dir="/agent",
            environment={},
            detach=True,
            labels={
                "platform.kind": "agent-inspection",
                "platform.image_tag": image_tag,
            },
        )
        container.start()
        result = container.wait(timeout=INSPECTION_TIMEOUT_SECONDS)
        exit_code = int(result.get("StatusCode", -1))
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace").strip()
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace").strip()

        if exit_code != 0:
            raise InspectionError(stderr or f"inspection container exited with code {exit_code}")

        payload = json.loads(stdout)
        if not isinstance(payload, dict):
            raise InspectionError("inspection output must be a JSON object")
        return payload
    except ImageNotFound as exc:
        raise InspectionError(f"inspection image {image_tag!r} not found") from exc
    except APIError as exc:
        raise InspectionError(f"docker API error during inspection: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InspectionError(f"inspection returned invalid JSON: {exc}") from exc
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
