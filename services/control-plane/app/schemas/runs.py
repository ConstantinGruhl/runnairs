from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunStartRequest(BaseModel):
    agent_slug: str
    inputs: dict[str, Any] | None = None


class RunPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    agent_version_id: uuid.UUID
    triggering_user_id: uuid.UUID | None
    trigger: str
    status: str
    inputs_json: dict[str, Any] | None
    result_json: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
