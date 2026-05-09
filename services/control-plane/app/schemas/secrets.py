from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceSecretPublic(BaseModel):
    """Workspace secret without the value — list/create/update return this."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class WorkspaceSecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_]+$")
    value: str = Field(min_length=1)


class WorkspaceSecretUpdate(BaseModel):
    value: str = Field(min_length=1)


class WorkspaceSecretReveal(BaseModel):
    id: uuid.UUID
    name: str
    value: str
