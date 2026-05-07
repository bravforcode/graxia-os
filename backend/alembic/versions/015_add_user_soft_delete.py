"""Add soft delete to User model

Revision ID: 015_add_user_soft_delete
Revises: 014_add_performance_indexes_phase2
Create Date: 2026-04-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_user_soft_delete"
down_revision: str | None = "014_add_performance_indexes_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_deleted_at",
        "users",
        ["deleted_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users", if_exists=True)
    op.drop_column("users", "deleted_at")
