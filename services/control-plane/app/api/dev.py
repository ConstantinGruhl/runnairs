from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.models import User

router = APIRouter(prefix="/dev", tags=["dev"])

DevOrAdmin = Annotated[User, Depends(require_role("developer", "admin"))]


@router.get("/agents")
def list_my_agents(actor: DevOrAdmin) -> dict[str, list]:
    # Real implementation lands in Phase 5 (agent deploy + CLI).
    return {"agents": []}
