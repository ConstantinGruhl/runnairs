from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.dependencies import DbSession, require_role
from app.models import Agent, AgentStatus, AgentVersion, User, UserRole, UserStatus
from app.schemas.admin_users import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AdminUserSummary,
    OneTimeCodeResponse,
)
from app.services.package_descriptor import normalize_stored_descriptor
from app.schemas.auth import UserPublic
from app.services import user_management_service

router = APIRouter(prefix="/admin", tags=["admin"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


@router.get("/users", response_model=list[AdminUserSummary])
def list_users(actor: AdminOnly, db: DbSession) -> list[AdminUserSummary]:
    rows = db.execute(select(User).where(User.tenant_id == actor.tenant_id)).scalars().all()
    return [AdminUserSummary.model_validate(u) for u in rows]


@router.post("/users", response_model=AdminUserSummary, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminCreateUserRequest,
    actor: AdminOnly,
    db: DbSession,
) -> AdminUserSummary:
    existing = db.execute(
        select(User).where(User.tenant_id == actor.tenant_id, User.email == payload.email)
    ).scalar_one_or_none()
    try:
        user = user_management_service.create_user(
            actor=actor,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            existing_user=existing,
        )
    except user_management_service.UserManagementConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except user_management_service.UserManagementValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminUserSummary.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserSummary)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequest,
    actor: AdminOnly,
    db: DbSession,
) -> AdminUserSummary:
    target = db.get(User, user_id)
    if target is None or target.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    active_admin_count = db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.tenant_id == actor.tenant_id,
            User.role == UserRole.admin,
            User.status == UserStatus.active,
        )
    ).scalar_one()
    try:
        user_management_service.update_user(
            actor=actor,
            target=target,
            role=payload.role,
            status=payload.status,
            active_admin_count=int(active_admin_count),
        )
    except user_management_service.UserManagementValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    db.commit()
    db.refresh(target)
    return AdminUserSummary.model_validate(target)


@router.post("/users/{user_id}/password-reset", response_model=OneTimeCodeResponse)
def generate_password_reset(
    user_id: uuid.UUID,
    actor: AdminOnly,
    db: DbSession,
) -> OneTimeCodeResponse:
    target = db.get(User, user_id)
    if target is None or target.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    code, expires_at = user_management_service.issue_password_reset(target=target)
    db.commit()
    return OneTimeCodeResponse(code=code, expires_at=expires_at, kind="password_reset")


@router.post("/users/{user_id}/recovery-code", response_model=OneTimeCodeResponse)
def generate_recovery_code(
    user_id: uuid.UUID,
    actor: AdminOnly,
    db: DbSession,
) -> OneTimeCodeResponse:
    target = db.get(User, user_id)
    if target is None or target.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    code, expires_at = user_management_service.issue_recovery_code(target=target)
    db.commit()
    return OneTimeCodeResponse(code=code, expires_at=expires_at, kind="recovery")


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
            "manifest": normalize_stored_descriptor(
                latest.manifest_json,
                descriptor_format=latest.descriptor_format,
            ),
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


@router.get("/diagnostics")
def diagnostics(actor: AdminOnly, db: DbSession) -> dict:
    return {
        "database": _check_database(db),
        "redis": _check_redis(),
        "tool_gateway": _check_tool_gateway(),
        "runtime_mode": os.getenv("PLATFORM_RUNTIME_MODE", "docker-socket"),
        "demo_dependencies_enabled": os.getenv("DEMO_DEPENDENCIES_ENABLED", "true").lower() == "true",
    }


def _check_database(db: DbSession) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _check_redis() -> str:
    try:
        client = redis.from_url(settings.redis_url)
        return "ok" if client.ping() else "error"
    except Exception:
        return "error"


def _check_tool_gateway() -> str:
    try:
        response = httpx.get(f"{settings.tool_gateway_url}/health", timeout=3.0)
        return "ok" if response.status_code == 200 else "error"
    except Exception:
        return "error"
