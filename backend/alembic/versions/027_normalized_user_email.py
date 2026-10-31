"""Enforce normalized, case-insensitive user email uniqueness.

Revision ID: 027_normalized_user_email
Revises: 026_openclaw_cost_precision
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "027_normalized_user_email"
down_revision: str | Sequence[str] | None = "026_openclaw_cost_precision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT lower(trim(email))
            FROM users
            GROUP BY lower(trim(email))
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce unique normalized user emails: duplicate normalized "
            "email values exist in users. Resolve duplicates explicitly before retrying."
        )

    op.create_index(
        "uq_users_normalized_email",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_normalized_email", table_name="users")
