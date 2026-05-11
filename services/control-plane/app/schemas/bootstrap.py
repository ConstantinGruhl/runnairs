from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.auth import UserPublic


class BootstrapChecks(BaseModel):
    jwt_secret_valid: bool
    platform_secrets_key_configured: bool
    database_ok: bool


class BootstrapStatePublic(BaseModel):
    bootstrap_required: bool
    completed: bool
    completed_at: str | None
    admin_created: bool
    instance_admin_user_id: str | None
    instance_admin_email: str | None
    tenant_id: str | None
    tenant_name: str | None
    notification_from_email: str | None
    auth_mode: str | None
    ready_for_completion: bool
    blocking_reasons: list[str]
    checks: BootstrapChecks


class BootstrapInitializeRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_password: str = Field(min_length=8, max_length=128)
    notification_from_email: str = Field(min_length=3, max_length=320)


class BootstrapConfigureRequest(BaseModel):
    tenant_name: str | None = Field(default=None, min_length=1, max_length=255)
    notification_from_email: str | None = Field(default=None, min_length=3, max_length=320)


class BootstrapInitializeResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
    state: BootstrapStatePublic
