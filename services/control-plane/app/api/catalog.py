from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.models import Agent, AgentStatus, AgentVersion, AutomationInstallation
from app.services import installations_service
from app.services.package_descriptor import normalize_stored_descriptor

router = APIRouter(prefix="/app", tags=["catalog"])


def _agent_card(
    *,
    agent: Agent,
    version: AgentVersion,
    installation: AutomationInstallation | None,
    available_workspace_connections: set[str],
    available_user_connections: set[str],
) -> dict:
    manifest = normalize_stored_descriptor(
        version.manifest_json,
        descriptor_format=version.descriptor_format,
    )
    tools = list(manifest.get("tools", []))
    approvals_required = list(manifest.get("approvals_required_for", []))
    user_connections = list(manifest.get("user_connections", []))
    modules = list(manifest.get("modules", []))
    installation_summary = installations_service.build_installation_summary(
        descriptor=manifest,
        installation=installation,
        available_workspace_connections=available_workspace_connections,
        available_user_connections=available_user_connections,
    )

    return {
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "version": version.version,
        "version_id": str(version.id),
        "tools": tools,
        "approvals_required_for": approvals_required,
        "user_secrets_needed": [{"name": name, "scope": "user"} for name in user_connections],
        "modules": modules,
        "installation": installation_summary,
    }


@router.get("/catalog")
def catalog(actor: CurrentUser, db: DbSession) -> dict:
    """List approved agents available to the caller's tenant."""
    rows = (
        db.execute(
            select(Agent, AgentVersion)
            .join(AgentVersion, AgentVersion.id == Agent.current_version_id)
            .where(
                Agent.tenant_id == actor.tenant_id,
                Agent.status == AgentStatus.approved,
            )
            .order_by(Agent.name)
        )
        .all()
    )
    workspace_connections = installations_service.available_workspace_connection_keys(
        db, tenant_id=actor.tenant_id
    )
    user_connections = installations_service.available_user_connection_keys(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
    )
    installation_rows = {
        row.agent_id: row
        for row in db.execute(
            select(AutomationInstallation).where(AutomationInstallation.tenant_id == actor.tenant_id)
        )
        .scalars()
        .all()
    }
    return {
        "agents": [
            _agent_card(
                agent=a,
                version=v,
                installation=installation_rows.get(a.id),
                available_workspace_connections=workspace_connections,
                available_user_connections=user_connections,
            )
            for a, v in rows
        ]
    }


@router.get("/catalog/{slug}")
def catalog_detail(slug: str, actor: CurrentUser, db: DbSession) -> dict:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None or agent.status != AgentStatus.approved or agent.current_version_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found in catalog")
    version = db.get(AgentVersion, agent.current_version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "current version disappeared")

    installation = db.execute(
        select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)
    ).scalar_one_or_none()
    card = _agent_card(
        agent=agent,
        version=version,
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
    manifest = normalize_stored_descriptor(
        version.manifest_json,
        descriptor_format=version.descriptor_format,
    )
    card["inputs"] = manifest.get("inputs", {}) or {}
    card["limits"] = manifest.get("limits", {}) or {}
    return card
