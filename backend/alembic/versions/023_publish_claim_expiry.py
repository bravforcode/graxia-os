"""add expiry metadata for durable Content Ops publish claims."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "023_publish_claim_expiry"
down_revision: str | None = "022_content_publish_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_publish_attempts",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_publish_attempts", "claim_expires_at")
