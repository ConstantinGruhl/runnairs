"""Build a per-agent Docker image from an uploaded zip.

Called from POST /dev/agents/deploy. Validates the manifest, picks
an auto-incremented version per agent, builds an image FROM the
agent-runtime base image with the agent's code COPY'd in, and writes
the AgentVersion row.
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
import yaml
from docker.errors import BuildError, DockerException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentStatus, AgentVersion

logger = logging.getLogger(__name__)

_BASE_IMAGE = "platform/agent-runtime:latest"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_REQUIRED_TOP_FIELDS = ("name", "entrypoint")


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

        manifest_path = tmp / "agent.yaml"
        if not manifest_path.exists():
            raise DeployError("archive is missing agent.yaml at the top level")
        if not (tmp / "main.py").exists():
            raise DeployError("archive is missing main.py at the top level")

        manifest = _load_manifest(manifest_path)
        slug = manifest["name"]

        agent = _upsert_agent(db, tenant_id=tenant_id, slug=slug, manifest=manifest, created_by=created_by)
        version = _next_version(db, agent.id)
        image_tag = f"agent-{agent.id}:{version}"

        _write_dockerfile(tmp)
        _build_image(tmp, image_tag)

        version_row = AgentVersion(
            agent_id=agent.id,
            version=version,
            manifest_json=manifest,
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


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise DeployError(f"agent.yaml parse error: {e}") from e
    if not isinstance(manifest, dict):
        raise DeployError("agent.yaml must be a mapping at the top level")

    for field in _REQUIRED_TOP_FIELDS:
        if not manifest.get(field):
            raise DeployError(f"agent.yaml missing required field: {field!r}")

    slug = manifest["name"]
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise DeployError(
            "agent.yaml `name` must match ^[a-z][a-z0-9-]{0,62}$ (lowercase, hyphens)"
        )
    if ":" not in str(manifest["entrypoint"]):
        raise DeployError("agent.yaml `entrypoint` must be in the form 'module:function'")

    permissions = manifest.get("permissions") or {}
    if not isinstance(permissions, dict):
        raise DeployError("agent.yaml `permissions` must be a mapping")
    tools = permissions.get("tools") or []
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise DeployError("agent.yaml `permissions.tools` must be a list of strings")
    secrets = permissions.get("secrets") or []
    if not isinstance(secrets, list):
        raise DeployError("agent.yaml `permissions.secrets` must be a list")
    for s in secrets:
        if not isinstance(s, dict) or "name" not in s or "scope" not in s:
            raise DeployError("each `permissions.secrets[]` must be {name, scope}")
        if s["scope"] not in ("workspace", "user"):
            raise DeployError("`permissions.secrets[].scope` must be 'workspace' or 'user'")
    http_allowlist = permissions.get("http_allowlist") or []
    if not isinstance(http_allowlist, list) or not all(isinstance(p, str) for p in http_allowlist):
        raise DeployError("agent.yaml `permissions.http_allowlist` must be a list of strings")
    if "http.request" in tools and not http_allowlist:
        raise DeployError(
            "agent.yaml declares http.request but has no permissions.http_allowlist"
        )

    return manifest


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
