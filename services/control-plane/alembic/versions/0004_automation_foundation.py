"""automation foundation

Revision ID: 0004
Revises: 0003
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_version",
        sa.Column("descriptor_format", sa.String(length=32), nullable=False, server_default="legacy_agent"),
    )
    op.add_column(
        "agent_version",
        sa.Column(
            "compatibility_version",
            sa.String(length=32),
            nullable=False,
            server_default="runtime_api:v1",
        ),
    )
    op.add_column(
        "agent_version",
        sa.Column("inspection_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    connection_scope = postgresql.ENUM(
        "workspace",
        "user",
        name="connection_scope",
        create_type=False,
    )
    connection_status = postgresql.ENUM(
        "pending",
        "ready",
        "invalid",
        name="connection_status",
        create_type=False,
    )
    installation_status = postgresql.ENUM(
        "draft",
        "ready",
        "active",
        "blocked",
        name="installation_status",
        create_type=False,
    )
    bind = op.get_bind()
    postgresql.ENUM("workspace", "user", name="connection_scope").create(bind, checkfirst=True)
    postgresql.ENUM("pending", "ready", "invalid", name="connection_status").create(bind, checkfirst=True)
    postgresql.ENUM("draft", "ready", "active", "blocked", name="installation_status").create(
        bind, checkfirst=True
    )

    op.create_table(
        "connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=False),
        sa.Column("scope", connection_scope, nullable=False),
        sa.Column(
            "status",
            connection_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "scopes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "secret_refs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connection_tenant_id", "connection", ["tenant_id"])
    op.create_index("ix_connection_user_id", "connection", ["user_id"])

    op.create_table(
        "automation_installation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            installation_status,
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "enabled_modules_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agent.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index("ix_automation_installation_tenant_id", "automation_installation", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_installation_tenant_id", table_name="automation_installation")
    op.drop_table("automation_installation")
    op.drop_index("ix_connection_user_id", table_name="connection")
    op.drop_index("ix_connection_tenant_id", table_name="connection")
    op.drop_table("connection")
    op.drop_column("agent_version", "inspection_json")
    op.drop_column("agent_version", "compatibility_version")
    op.drop_column("agent_version", "descriptor_format")

    bind = op.get_bind()
    postgresql.ENUM(name="installation_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="connection_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="connection_scope").drop(bind, checkfirst=True)
