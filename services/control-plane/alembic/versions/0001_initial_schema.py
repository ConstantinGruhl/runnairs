"""initial schema

Initial migration: creates every table from the SQLAlchemy metadata.
Subsequent migrations must use explicit op.create_table / op.alter_column
so changes can be reviewed in diff.

Revision ID: 0001
Revises:
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.models import Base

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
