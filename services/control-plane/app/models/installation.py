from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, jsonb_col, uuid_pk


class InstallationStatus(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    active = "active"
    blocked = "blocked"


class AutomationInstallation(Base):
    __tablename__ = "automation_installation"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[InstallationStatus] = mapped_column(
        Enum(InstallationStatus, name="installation_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=InstallationStatus.draft,
    )
    enabled_modules_json: Mapped[list[str]] = jsonb_col(default=list)
    config_json: Mapped[dict[str, Any]] = jsonb_col(default=dict)
    last_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
