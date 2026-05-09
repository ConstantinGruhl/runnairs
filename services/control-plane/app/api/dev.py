from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Agent, AgentVersion, User
from app.services import agent_deploy_service

router = APIRouter(prefix="/dev", tags=["dev"])

DevOrAdmin = Annotated[User, Depends(require_role("developer", "admin"))]

_MAX_ARCHIVE_BYTES = 10 * 1024 * 1024  # 10 MB


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
