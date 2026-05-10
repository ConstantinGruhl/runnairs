from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Agent, AgentVersion, AutomationInstallation, User
from app.services import agent_deploy_service, installations_service
from app.services.package_descriptor import normalize_stored_descriptor

router = APIRouter(prefix="/dev", tags=["dev"])

DevOrAdmin = Annotated[User, Depends(require_role("developer", "admin"))]

_MAX_ARCHIVE_BYTES = 10 * 1024 * 1024  # 10 MB


class AutomationScaffoldRequest(BaseModel):
    slug: str
    display_name: str
    modules: list[str] = Field(default_factory=lambda: ["default"])


@router.get("/agents")
def list_my_agents(actor: DevOrAdmin, db: DbSession) -> dict:
    rows = (
        db.execute(
            select(Agent)
            .where(Agent.tenant_id == actor.tenant_id)
            .order_by(Agent.created_at.desc())
        )
        .scalars()
        .all()
    )
    agents = []
    for a in rows:
        version_count = db.execute(
            select(AgentVersion).where(AgentVersion.agent_id == a.id)
        ).all()
        agents.append({
            "id": str(a.id),
            "slug": a.slug,
            "name": a.name,
            "description": a.description,
            "status": a.status.value,
            "current_version_id": str(a.current_version_id) if a.current_version_id else None,
            "version_count": len(version_count),
            "created_at": a.created_at.isoformat(),
        })
    return {"agents": agents}


@router.get("/agents/{slug}")
def get_agent(slug: str, actor: DevOrAdmin, db: DbSession) -> dict:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    versions = (
        db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(AgentVersion.created_at.desc())
        )
        .scalars()
        .all()
    )
    current_version = versions[0] if versions else None
    installation = db.execute(
        select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)
    ).scalar_one_or_none()
    manifest = (
        normalize_stored_descriptor(
            current_version.manifest_json,
            descriptor_format=current_version.descriptor_format,
        )
        if current_version is not None
        else {}
    )
    return {
        "id": str(agent.id),
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "status": agent.status.value,
        "current_version_id": str(agent.current_version_id) if agent.current_version_id else None,
        "modules": manifest.get("modules", []),
        "installation": installations_service.build_installation_summary(
            descriptor=manifest,
            installation=installation,
            available_workspace_connections=installations_service.available_workspace_connection_keys(
                db, tenant_id=actor.tenant_id
            ),
            available_user_connections=installations_service.available_user_connection_keys(
                db,
                tenant_id=actor.tenant_id,
                user_id=actor.id,
            ),
        )
        if current_version is not None
        else None,
        "versions": [
            {
                "id": str(v.id),
                "version": v.version,
                "image_tag": v.image_tag,
                "descriptor_format": v.descriptor_format,
                "inspection": v.inspection_json,
                "created_at": v.created_at.isoformat(),
                "approved_at": v.approved_at.isoformat() if v.approved_at else None,
                "is_current": agent.current_version_id == v.id,
            }
            for v in versions
        ],
    }


@router.post("/agents/deploy", status_code=status.HTTP_201_CREATED)
async def deploy_agent(
    actor: DevOrAdmin,
    db: DbSession,
    archive: UploadFile,
) -> dict:
    archive_bytes = await archive.read()
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"archive exceeds {_MAX_ARCHIVE_BYTES} bytes",
        )

    try:
        result = agent_deploy_service.deploy(
            db,
            tenant_id=actor.tenant_id,
            created_by=actor.id,
            archive_bytes=archive_bytes,
        )
    except agent_deploy_service.DeployError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    return {
        "agent_id": str(result.agent_id),
        "slug": result.slug,
        "version": result.version,
        "image_tag": result.image_tag,
        "status": result.status,
    }


def render_automation_yaml(slug: str, display_name: str, modules: list[str]) -> str:
    return __import__("yaml").safe_dump(
        {
            "name": slug,
            "display_name": display_name,
            "description": f"TODO - describe what {display_name} does.",
            "runtime": "python3.12",
            "entrypoint": "main:run",
            "compatibility": {"runtime_api": "v2"},
            "inputs": {},
            "modules": [
                {
                    "id": module_id,
                    "title": module_id.replace("_", " ").title(),
                    "required": index == 0,
                    "enabled_by_default": True,
                }
                for index, module_id in enumerate(modules)
            ],
            "tools": [],
            "limits": {
                "timeout_seconds": 60,
                "memory_mb": 256,
                "max_tokens": 5000,
                "max_cost_usd": 0.50,
            },
        },
        sort_keys=False,
    )


def render_automation_main(modules: list[str]) -> str:
    return (
        "AUTOMATION_META = "
        + json.dumps(
            {
                "runtime_api": "v2",
                "modules": [{"id": module_id} for module_id in modules],
                "triggers": ["manual"],
            },
            indent=2,
        )
        + "\n\n"
        + "def run() -> dict:\n"
        + '    return {"ok": True}\n'
    )


def render_automation_test() -> str:
    return (
        "from main import run\n\n"
        "def test_run_returns_ok() -> None:\n"
        '    assert run()["ok"] is True\n'
    )


@router.post("/automation-scaffold")
def automation_scaffold(payload: AutomationScaffoldRequest, actor: DevOrAdmin) -> dict[str, str]:
    files = {
        "automation.yaml": render_automation_yaml(
            payload.slug,
            payload.display_name,
            payload.modules or ["default"],
        ),
        "main.py": render_automation_main(payload.modules or ["default"]),
        "README.md": f"# {payload.display_name}\n\nNative automation package scaffold.\n",
        "AI_INSTRUCTIONS.md": (
            "Build inside the declared module boundaries.\n"
            "Prefer updating automation.yaml over adding sidecar config files when metadata changes.\n"
        ),
        "tests/test_agent.py": render_automation_test(),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative_path, content in files.items():
            zf.writestr(relative_path, content)
    return {
        "filename": f"{payload.slug}.zip",
        "archive_base64": base64.b64encode(buffer.getvalue()).decode(),
    }
