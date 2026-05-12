from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models import SkillSource, User
from app.schemas.skill_registry import SkillSourceDetail, SkillSourceSummary, SkillSourceUpsertRequest
from app.services import skill_registry_service

router = APIRouter(prefix="/admin/skill-sources", tags=["skill-registry"])
app_router = APIRouter(prefix="/app/skills", tags=["skill-registry"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


@router.get("", response_model=list[SkillSourceSummary])
def list_skill_sources(actor: AdminOnly, db: DbSession) -> list[SkillSourceSummary]:
    rows = skill_registry_service.list_skill_sources(db, tenant_id=actor.tenant_id)
    return [skill_registry_service.serialize_skill_source_summary(row) for row in rows]


@router.get("/{slug}", response_model=SkillSourceDetail)
def get_skill_source(slug: str, actor: AdminOnly, db: DbSession) -> SkillSourceDetail:
    source = skill_registry_service.get_skill_source(db, tenant_id=actor.tenant_id, slug=slug)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill source not found")
    return skill_registry_service.serialize_skill_source_detail(source)


@router.put("/{slug}", response_model=SkillSourceDetail)
def upsert_skill_source(
    slug: str,
    payload: SkillSourceUpsertRequest,
    actor: AdminOnly,
    db: DbSession,
) -> SkillSourceDetail:
    try:
        source = skill_registry_service.upsert_skill_source(
            db,
            tenant_id=actor.tenant_id,
            slug=slug,
            repo_url=payload.repo_url,
            git_ref=payload.git_ref,
            created_by=actor.id,
            storage_root=settings.skill_registry_root,
        )
    except skill_registry_service.SkillRegistryError as exc:
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    db.refresh(source)
    return skill_registry_service.serialize_skill_source_detail(source)


@router.post("/{slug}/refresh", response_model=SkillSourceDetail)
def refresh_skill_source(slug: str, actor: AdminOnly, db: DbSession) -> SkillSourceDetail:
    source = skill_registry_service.get_skill_source(db, tenant_id=actor.tenant_id, slug=slug)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill source not found")

    try:
        source = skill_registry_service.refresh_skill_source(
            db,
            source=source,
            storage_root=settings.skill_registry_root,
            expected_slug=source.slug,
        )
    except skill_registry_service.SkillRegistryError as exc:
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    db.refresh(source)
    return skill_registry_service.serialize_skill_source_detail(source)


@app_router.get("", response_model=list[SkillSourceSummary])
def list_ready_skill_sources(actor: CurrentUser, db: DbSession) -> list[SkillSourceSummary]:
    rows = skill_registry_service.list_skill_sources(
        db,
        tenant_id=actor.tenant_id,
        ready_only=True,
    )
    return [skill_registry_service.serialize_skill_source_summary(row) for row in rows]


@app_router.get("/{slug}", response_model=SkillSourceDetail)
def get_ready_skill_source(slug: str, actor: CurrentUser, db: DbSession) -> SkillSourceDetail:
    source = skill_registry_service.get_skill_source(
        db,
        tenant_id=actor.tenant_id,
        slug=slug,
        ready_only=True,
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "skill source not found")
    return skill_registry_service.serialize_skill_source_detail(source)
