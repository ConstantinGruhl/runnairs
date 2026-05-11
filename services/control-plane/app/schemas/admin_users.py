from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole, UserStatus


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    status: UserStatus
    must_reset_password: bool
    password_changed_at: datetime
    created_at: datetime


class AdminCreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole


class AdminUpdateUserRequest(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None


class OneTimeCodeResponse(BaseModel):
    code: str
    expires_at: str | None
    kind: str
