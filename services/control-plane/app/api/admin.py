from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Agent, AgentStatus, AgentVersion, User
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/admin", tags=["admin"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


@router.get("/users", response_model=list[UserPublic])
def list_users(actor: AdminOnly, db: DbSession) -> list[UserPublic]:
    rows = db.execute(select(User).where(User.tenant_id == actor.tenant_id)).scalars().all()
    return [UserPublic.model_validate(u) for u in rows]


@router.get("/whoami")
def whoami(actor: AdminOnly) -> dict[str, uuid.UUID | str]:
    return {"id": actor.id, "role": actor.role.value, "tenant_id": actor.tenant_id}


@router.get("/agents/pending")
def list_pending_agents(actor: AdminOnly, db: DbSession) -> dict:
    """Agents with at least one un-approved version."""
    rows = (
        db.execute(
            select(Agent)
            .where(Agent.tenant_id == actor.tenant_id, Agent.status != AgentStatus.archived)
            .order_by(Agent.created_at.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for agent in rows:
        latest = db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(AgentVersion.created_at.desc())
        ).scalar()
        if latest is None:
            continue
        out.append({
            "agent_id": str(agent.id),
            "slug": agent.slug,
            "name": agent.name,
            "status": agent.status.value,
            "latest_version": latest.version,
            "latest_version_id": str(latest.id),
            "approved": latest.approved_by is not None,
            "manifest": latest.manifest_json,
        })
    return {"agents": out}


@router.post("/agents/{slug}/approve")
def approve_agent(slug: str, actor: AdminOnly, db: DbSession) -> dict:
    """Approve the latest version of an agent for the catalog."""
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")

    latest = db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.created_at.desc())
    ).scalar()
    if latest is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "agent has no versions to approve")

    if latest.approved_by is None:
        latest.approved_by = actor.id
        latest.approved_at = datetime.now(timezone.utc)
    agent.current_version_id = latest.id
    agent.status = AgentStatus.approved
    db.commit()

    return {
        "agent_id": str(agent.id),
        "slug": agent.slug,
        "version": latest.version,
        "version_id": str(latest.id),
        "status": agent.status.value,
    }
