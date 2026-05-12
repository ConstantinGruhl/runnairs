"""git-backed skill registry metadata

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("repo_url", sa.String(length=1024), nullable=False),
        sa.Column("git_ref", sa.String(length=255), nullable=False, server_default="HEAD"),
        sa.Column("resolved_commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "ready", "error", name="skill_source_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("descriptor_format", sa.String(length=32), nullable=True),
        sa.Column(
            "manifest_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "tree_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("instructions_markdown", sa.Text(), nullable=True),
        sa.Column("extracted_root", sa.String(length=1024), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_skill_source_tenant_slug"),
    )
    op.create_index("ix_skill_source_tenant_id", "skill_source", ["tenant_id"])
    op.create_index("ix_skill_source_agent_id", "skill_source", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_skill_source_agent_id", table_name="skill_source")
    op.drop_index("ix_skill_source_tenant_id", table_name="skill_source")
    op.drop_table("skill_source")
    op.execute("DROP TYPE skill_source_status")
