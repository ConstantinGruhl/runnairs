"""built-in iam foundation user columns

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_status = postgresql.ENUM("active", "disabled", name="user_status")
    user_status.create(op.get_bind(), checkfirst=True)

    op.add_column("user", sa.Column("status", user_status, nullable=False, server_default="active"))
    op.add_column(
        "user",
        sa.Column("must_reset_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "user",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("user", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("user", sa.Column("password_reset_code_hash", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("password_reset_code_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("recovery_code_hash", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("recovery_code_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "recovery_code_expires_at")
    op.drop_column("user", "recovery_code_hash")
    op.drop_column("user", "password_reset_code_expires_at")
    op.drop_column("user", "password_reset_code_hash")
    op.drop_column("user", "session_version")
    op.drop_column("user", "password_changed_at")
    op.drop_column("user", "must_reset_password")
    op.drop_column("user", "status")

    user_status = postgresql.ENUM("active", "disabled", name="user_status")
    user_status.drop(op.get_bind(), checkfirst=True)
