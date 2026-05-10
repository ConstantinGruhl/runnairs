from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, jsonb_col, uuid_pk


class ConnectionScope(str, enum.Enum):
    workspace = "workspace"
    user = "user"


class ConnectionStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    invalid = "invalid"


class Connection(Base):
    __tablename__ = "connection"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[ConnectionScope] = mapped_column(
        Enum(ConnectionScope, name="connection_scope", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConnectionScope.workspace,
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connection_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConnectionStatus.pending,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes_json: Mapped[list[str]] = jsonb_col(default=list)
    config_json: Mapped[dict[str, Any]] = jsonb_col(default=dict)
    secret_refs_json: Mapped[dict[str, str]] = jsonb_col(default=dict)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
