from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk


class SecretScope(str, enum.Enum):
    workspace = "workspace"
    user = "user"


class Secret(Base):
    __tablename__ = "secret"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scope", "owner_user_id", "name", name="uq_secret_unique"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[SecretScope] = mapped_column(
        Enum(SecretScope, name="secret_scope", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class SecretGrant(Base):
    __tablename__ = "secret_grant"
    __table_args__ = (
        UniqueConstraint("agent_id", "secret_name", "scope", name="uq_secret_grant"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, index=True
    )
    secret_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[SecretScope] = mapped_column(
        Enum(SecretScope, name="secret_scope", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=False,
    )
