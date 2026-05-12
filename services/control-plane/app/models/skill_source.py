from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, jsonb_col, updated_at_col, uuid_pk


class SkillSourceStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    error = "error"


class SkillSource(Base):
    __tablename__ = "skill_source"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_skill_source_tenant_slug"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    git_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="HEAD")
    resolved_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SkillSourceStatus] = mapped_column(
        Enum(
            SkillSourceStatus,
            name="skill_source_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=SkillSourceStatus.pending,
    )
    descriptor_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    manifest_json: Mapped[dict[str, Any] | None] = jsonb_col(nullable=True)
    tree_json: Mapped[list[dict[str, Any]]] = jsonb_col(default=list)
    instructions_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_root: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
