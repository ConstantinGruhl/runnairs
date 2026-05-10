from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Agent, AgentVersion, AutomationInstallation, InstallationStatus, User
from app.services import installations_service
from app.services.package_descriptor import normalize_stored_descriptor

router = APIRouter(prefix="/admin", tags=["installations"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


class InstallationUpdate(BaseModel):
    enabled_modules: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


@router.get("/agents/{slug}/installation")
def get_installation(slug: str, actor: AdminOnly, db: DbSession) -> dict[str, Any]:
    agent = _agent_or_404(db, actor, slug)
    version = _version_for_agent(db, agent)
    installation = db.execute(
        select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)
    ).scalar_one_or_none()
    manifest = normalize_stored_descriptor(
        version.manifest_json,
        descriptor_format=version.descriptor_format,
    )
    summary = installations_service.build_installation_summary(
        descriptor=manifest,
        installation=installation,
        available_workspace_connections=installations_service.available_workspace_connection_keys(
            db, tenant_id=actor.tenant_id
        ),
        available_user_connections=set(),
    )
    return {
        "agent_id": str(agent.id),
        "version_id": str(version.id),
        "modules": manifest.get("modules", []),
        **summary,
    }


@router.put("/agents/{slug}/installation")
def upsert_installation(
    slug: str,
    payload: InstallationUpdate,
    actor: AdminOnly,
    db: DbSession,
) -> dict[str, Any]:
    agent = _agent_or_404(db, actor, slug)
    version = _version_for_agent(db, agent)
    installation = db.execute(
        select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)
    ).scalar_one_or_none()
    if installation is None:
        installation = AutomationInstallation(agent_id=agent.id, tenant_id=actor.tenant_id)
        db.add(installation)

    installation.enabled_modules_json = list(payload.enabled_modules)
    installation.config_json = dict(payload.config)
    manifest = normalize_stored_descriptor(
        version.manifest_json,
        descriptor_format=version.descriptor_format,
    )
    summary = installations_service.build_installation_summary(
        descriptor=manifest,
        installation=installation,
        available_workspace_connections=installations_service.available_workspace_connection_keys(
            db, tenant_id=actor.tenant_id
        ),
        available_user_connections=set(),
    )
    installation.status = InstallationStatus(summary["status"])
    db.commit()
    db.refresh(installation)

    return {
        "agent_id": str(agent.id),
        "version_id": str(version.id),
        "modules": manifest.get("modules", []),
        **summary,
    }


def _agent_or_404(db: DbSession, actor: User, slug: str) -> Agent:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return agent


def _version_for_agent(db: DbSession, agent: Agent) -> AgentVersion:
    version = None
    if agent.current_version_id is not None:
        version = db.get(AgentVersion, agent.current_version_id)
    if version is None:
        version = db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(AgentVersion.created_at.desc())
        ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "agent has no deployed versions")
    return version
