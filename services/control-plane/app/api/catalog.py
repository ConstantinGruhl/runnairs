from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser

router = APIRouter(prefix="/app", tags=["catalog"])


@router.get("/catalog")
def catalog(_: CurrentUser) -> dict[str, list]:
    # Real implementation lands in Phase 6 (catalog + run UI).
    return {"agents": []}
