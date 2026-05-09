"""drop audit_log FKs to run / agent / user

Audit rows must be append-only and survive deletion of the records
they reference. The columns stay; only the constraints go.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FKS = [
    "audit_log_run_id_fkey",
    "audit_log_agent_id_fkey",
    "audit_log_user_id_fkey",
]


def upgrade() -> None:
    for name in _FKS:
        op.drop_constraint(name, "audit_log", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "audit_log_run_id_fkey", "audit_log", "run",
        ["run_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_log_agent_id_fkey", "audit_log", "agent",
        ["agent_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_log_user_id_fkey", "audit_log", "user",
        ["user_id"], ["id"], ondelete="SET NULL",
    )
