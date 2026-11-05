"""Preserve sub-cent LLM costs in usage records.

Revision ID: 036_openclaw_cost_precision
Revises: 035_unique_social_provider_subject
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "036_openclaw_cost_precision"
down_revision: str | Sequence[str] | None = "035_unique_social_provider_subject"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("openclaw_usage") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            existing_type=sa.Numeric(10, 4),
            type_=sa.Numeric(20, 12),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("openclaw_usage") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            existing_type=sa.Numeric(20, 12),
            type_=sa.Numeric(10, 4),
            existing_nullable=False,
        )
