from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.auth import UserPublic


class BootstrapChecks(BaseModel):
    jwt_secret_valid: bool
    platform_secrets_key_configured: bool
    database_ok: bool


class BootstrapGuidanceItem(BaseModel):
    key: str
    category: str
    title: str
    body: str
    action: str


class BootstrapOidcProviderState(BaseModel):
    exists: bool
    is_enabled: bool
    name: str | None


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
    supported_auth_modes: list[str]
    built_in_login_enabled: bool
    oidc_provider_state: BootstrapOidcProviderState
    ready_for_completion: bool
    blocking_reasons: list[str]
    operator_guidance: list[BootstrapGuidanceItem]
    checks: BootstrapChecks


class BootstrapInitializeRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_password: str = Field(min_length=8, max_length=128)
    notification_from_email: str = Field(min_length=3, max_length=320)
    auth_mode: str = Field(min_length=1, max_length=64)


class BootstrapConfigureRequest(BaseModel):
    tenant_name: str | None = Field(default=None, min_length=1, max_length=255)
    notification_from_email: str | None = Field(default=None, min_length=3, max_length=320)
    auth_mode: str | None = Field(default=None, min_length=1, max_length=64)


class BootstrapInitializeResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    bootstrap_recovery_code: str | None = None
    user: UserPublic
    state: BootstrapStatePublic
