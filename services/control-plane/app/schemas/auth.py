from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


class PasswordResetCompleteRequest(BaseModel):
    email: str
    reset_code: str
    new_password: str


class RecoveryCompleteRequest(BaseModel):
    email: str
    recovery_code: str
    new_password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    tenant_id: uuid.UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


