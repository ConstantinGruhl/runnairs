from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import User
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
