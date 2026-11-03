"""Expand Alembic version storage before migration 014 writes its long ID.

Revision ID: 014a_expand_version
Revises: 89d09d4d6b03
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014a_expand_version"
down_revision: str | None = "89d09d4d6b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the version table able to store existing and future revision IDs.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Alembic downgrades to 89d09d4d6b03 before this change is reversed;
    # that revision fits VARCHAR(32), so this remains reversible.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
