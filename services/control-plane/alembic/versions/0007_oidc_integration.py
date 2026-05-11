"""oidc integration: providers, user identities, auth requests, and nullable password_hash

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("user", "password_hash", existing_type=sa.String(length=255), nullable=True)

    op.create_table(
        "oidc_provider",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("discovery_url", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=512), nullable=False),
        sa.Column("client_secret_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "scopes",
            sa.String(length=512),
            nullable=False,
            server_default="openid email profile",
        ),
        sa.Column(
            "email_claim",
            sa.String(length=128),
            nullable=False,
            server_default="email",
        ),
        sa.Column("role_claim", sa.String(length=128), nullable=True),
        sa.Column(
            "claim_role_map",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "default_role",
            sa.String(length=32),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "allow_jit_provisioning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "manage_roles",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
    )

    op.create_table(
        "user_identity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oidc_provider.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("email_at_login", sa.String(length=320), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("provider_id", "subject", name="uq_user_identity_provider_subject"),
    )
    op.create_index("ix_user_identity_user_id", "user_identity", ["user_id"])
    op.create_index("ix_user_identity_provider_id", "user_identity", ["provider_id"])

    op.create_table(
        "oidc_auth_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oidc_provider.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("pkce_verifier", sa.String(length=255), nullable=False),
        sa.Column("redirect_after_login", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_oidc_auth_request_provider_id", "oidc_auth_request", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_oidc_auth_request_provider_id", table_name="oidc_auth_request")
    op.drop_table("oidc_auth_request")
    op.drop_index("ix_user_identity_provider_id", table_name="user_identity")
    op.drop_index("ix_user_identity_user_id", table_name="user_identity")
    op.drop_table("user_identity")
    op.drop_table("oidc_provider")

    op.alter_column("user", "password_hash", existing_type=sa.String(length=255), nullable=False)
