from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk
from app.models.user import UserRole


class OidcProvider(Base):
    __tablename__ = "oidc_provider"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    discovery_url: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scopes: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="openid email profile",
        server_default="openid email profile",
    )
    email_claim: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="email",
        server_default="email",
    )
    role_claim: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_role_map: Mapped[dict[str, str]] = jsonb_col(default=dict)
    default_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=UserRole.user.value,
        server_default=UserRole.user.value,
    )
    allow_jit_provisioning: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    manage_roles: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
