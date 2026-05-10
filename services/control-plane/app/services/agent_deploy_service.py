"""Build a per-agent Docker image from an uploaded zip.

Called from POST /dev/agents/deploy. Validates the manifest, picks
an auto-incremented version per agent, builds an image FROM the
agent-runtime base image with the agent's code COPY'd in, and writes
the AgentVersion row.
"""
from __future__ import annotations

import io
import importlib
import logging
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from docker.errors import BuildError, DockerException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentStatus, AgentVersion
from app.services.package_descriptor import load_package_descriptor

logger = logging.getLogger(__name__)

_BASE_IMAGE = "platform/agent-runtime:latest"


class DeployError(Exception):
    """Raised for any user-facing error during deploy."""


@dataclass
class DeployedAgent:
    agent_id: uuid.UUID
    slug: str
    version: str
    image_tag: str
    status: str


def deploy(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    archive_bytes: bytes,
) -> DeployedAgent:
    with tempfile.TemporaryDirectory(prefix="agent-deploy-") as tmpdir:
        tmp = Path(tmpdir)
        _safe_extract(archive_bytes, tmp)

        if not (tmp / "main.py").exists():
            raise DeployError("archive is missing main.py at the top level")

        try:
            descriptor = load_package_descriptor(tmp)
        except ValueError as e:
            raise DeployError(str(e)) from e

        manifest = descriptor.data
        slug = manifest["name"]
        try:
            inspection = inspect_package(tmp, manifest["entrypoint"])
            validate_descriptor_against_inspection(manifest, inspection)
        except ValueError as e:
            raise DeployError(str(e)) from e

        agent = _upsert_agent(db, tenant_id=tenant_id, slug=slug, manifest=manifest, created_by=created_by)
        version = _next_version(db, agent.id)
        image_tag = f"agent-{agent.id}:{version}"

        _write_dockerfile(tmp)
        _build_image(tmp, image_tag)

        version_row = AgentVersion(
            agent_id=agent.id,
            version=version,
            manifest_json=manifest,
            descriptor_format=descriptor.format,
            compatibility_version=_compatibility_version(manifest),
            inspection_json=inspection,
            image_tag=image_tag,
            created_by=created_by,
        )
        db.add(version_row)
        db.flush()

    db.commit()
    return DeployedAgent(
        agent_id=agent.id,
        slug=agent.slug,
        version=version,
        image_tag=image_tag,
        status=agent.status.value,
    )


def _safe_extract(archive_bytes: bytes, target: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            for name in zf.namelist():
                if name.startswith("/") or ".." in Path(name).parts:
                    raise DeployError(f"unsafe path in archive: {name!r}")
                if "\x00" in name:
                    raise DeployError(f"null byte in archive entry: {name!r}")
            zf.extractall(target)
    except zipfile.BadZipFile as e:
        raise DeployError(f"archive is not a valid zip file: {e}") from e


def inspect_package(root: Path, entrypoint: str) -> dict[str, Any]:
    module_name, function_name = entrypoint.split(":", 1)
    sys_path_added = False
    importlib.invalidate_caches()
    original_module = sys.modules.pop(module_name, None)
    try:
        sys.path.insert(0, str(root))
        sys_path_added = True
        module = importlib.import_module(module_name)
    finally:
        if sys_path_added and sys.path and sys.path[0] == str(root):
            sys.path.pop(0)
        if original_module is not None:
            sys.modules[module_name] = original_module
        else:
            sys.modules.pop(module_name, None)

    if not hasattr(module, function_name):
        raise ValueError(f"entrypoint {entrypoint!r} is missing")

    meta = getattr(module, "AUTOMATION_META", {})
    if meta and not isinstance(meta, dict):
        raise ValueError("AUTOMATION_META must be a mapping when provided")

    module_specs = meta.get("modules", []) if isinstance(meta, dict) else []
    modules = [
        module_spec["id"]
        for module_spec in module_specs
        if isinstance(module_spec, dict) and module_spec.get("id")
    ]
    if not modules:
        modules = ["default"]

    return {
        "runtime_api": meta.get("runtime_api", "v1") if isinstance(meta, dict) else "v1",
        "modules": modules,
        "triggers": list(meta.get("triggers", ["manual"])) if isinstance(meta, dict) else ["manual"],
        "channels": list(meta.get("channels", [])) if isinstance(meta, dict) else [],
        "entrypoint": entrypoint,
    }


def validate_descriptor_against_inspection(descriptor: dict[str, Any], inspection: dict[str, Any]) -> None:
    declared_modules = {module["id"] for module in descriptor.get("modules", []) if isinstance(module, dict)}
    implemented_modules = set(inspection.get("modules", []))
    missing_modules = sorted(declared_modules - implemented_modules)
    if missing_modules:
        raise ValueError(f"descriptor declares modules with no implementation: {missing_modules}")

    expected_runtime_api = (descriptor.get("compatibility") or {}).get("runtime_api", "v1")
    if inspection.get("runtime_api") != expected_runtime_api:
        raise ValueError("descriptor runtime_api does not match inspected runtime_api")


def _compatibility_version(manifest: dict[str, Any]) -> str:
    runtime_api = (manifest.get("compatibility") or {}).get("runtime_api", "v1")
    return f"runtime_api:{runtime_api}"


def _upsert_agent(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    slug: str,
    manifest: dict[str, Any],
    created_by: uuid.UUID,
) -> Agent:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is not None:
        # Refresh metadata that came with the new version.
        if manifest.get("display_name"):
            agent.name = manifest["display_name"]
        if manifest.get("description"):
            agent.description = manifest["description"]
        return agent

    agent = Agent(
        tenant_id=tenant_id,
        slug=slug,
        name=manifest.get("display_name") or slug,
        description=manifest.get("description"),
        created_by=created_by,
        status=AgentStatus.draft,
    )
    db.add(agent)
    db.flush()
    return agent


def _next_version(db: Session, agent_id: uuid.UUID) -> str:
    count = db.execute(
        select(func.count(AgentVersion.id)).where(AgentVersion.agent_id == agent_id)
    ).scalar_one()
    return f"v{count + 1}"


def _write_dockerfile(target: Path) -> None:
    (target / "Dockerfile").write_text(
        f"FROM {_BASE_IMAGE}\n"
        f"COPY . /agent/\n"
    )


def _build_image(context: Path, tag: str) -> None:
    try:
        client = docker.from_env()
    except DockerException as e:
        raise DeployError(f"cannot reach docker daemon: {e}") from e

    logger.info("building image %s from %s", tag, context)
    try:
        _, logs = client.images.build(
            path=str(context),
            tag=tag,
            rm=True,
            forcerm=True,
            pull=False,
        )
        for chunk in logs:
            stream = chunk.get("stream") if isinstance(chunk, dict) else None
            if stream:
                logger.info("docker build: %s", stream.rstrip())
    except BuildError as e:
        raise DeployError(f"image build failed: {e.msg}") from e
    except DockerException as e:
        raise DeployError(f"docker error during build: {e}") from e
