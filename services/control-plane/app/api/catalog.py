from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.models import Agent, AgentStatus, AgentVersion

router = APIRouter(prefix="/app", tags=["catalog"])


def _agent_card(agent: Agent, version: AgentVersion) -> dict:
    manifest = version.manifest_json or {}
    permissions = manifest.get("permissions", {}) or {}
    tools = list(permissions.get("tools", []))
    secrets = permissions.get("secrets", []) or []
    user_secrets = [s for s in secrets if isinstance(s, dict) and s.get("scope") == "user"]
    approvals = manifest.get("approvals", {}) or {}
    approvals_required = list(approvals.get("required_for", []))

    return {
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "version": version.version,
        "version_id": str(version.id),
        "tools": tools,
        "approvals_required_for": approvals_required,
        "user_secrets_needed": [{"name": s["name"], "scope": s["scope"]} for s in user_secrets],
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
    return {"agents": [_agent_card(a, v) for a, v in rows]}


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

    card = _agent_card(agent, version)
    manifest = version.manifest_json or {}
    card["inputs"] = manifest.get("inputs", {}) or {}
    card["limits"] = manifest.get("limits", {}) or {}
    return card
