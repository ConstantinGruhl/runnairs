from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OidcDiscoveryProbeRequest(BaseModel):
    discovery_url: str = Field(min_length=1, max_length=512)


class OidcDiscoveryProbeResponse(BaseModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes_supported: list[str] = []
    response_types_supported: list[str] = []


class OidcProviderPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    issuer: str
    discovery_url: str
    client_id: str
    has_client_secret: bool
    scopes: str
    email_claim: str
    role_claim: str | None
    claim_role_map: dict[str, str]
    default_role: str
    allow_jit_provisioning: bool
    manage_roles: bool
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class OidcProviderUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    issuer: str = Field(min_length=1, max_length=512)
    discovery_url: str = Field(min_length=1, max_length=512)
    client_id: str = Field(min_length=1, max_length=512)
    client_secret: str | None = Field(default=None, max_length=2048)
    scopes: str = Field(default="openid email profile", min_length=1, max_length=512)
    email_claim: str = Field(default="email", min_length=1, max_length=128)
    role_claim: str | None = Field(default=None, max_length=128)
    claim_role_map: dict[str, str] = Field(default_factory=dict)
    default_role: str = Field(default="user")
    allow_jit_provisioning: bool = True
    manage_roles: bool = False
    is_enabled: bool = False
    rotate_secret: bool = False
