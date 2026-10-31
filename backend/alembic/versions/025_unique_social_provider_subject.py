"""Enforce one local account per Supabase subject.

Revision ID: 025_unique_social_provider_subject
Revises: 024_organic_attribution_consent
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "025_unique_social_provider_subject"
down_revision: str | Sequence[str] | None = "024_organic_attribution_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_users_provider_id"


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT provider_id
            FROM users
            WHERE provider_id IS NOT NULL
            GROUP BY provider_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce unique social provider subjects: duplicate provider_id "
            "values exist in users. Resolve duplicates explicitly before retrying."
        )

    op.create_index(
        INDEX_NAME,
        "users",
        ["provider_id"],
        unique=True,
        postgresql_where=sa.text("provider_id IS NOT NULL"),
        sqlite_where=sa.text("provider_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="users")
