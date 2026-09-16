"""durable Content Ops publish attempts.

Stores only tenant-scoped request identity and redacted provider receipts. Raw
provider payloads, tokens, and exception text are intentionally not persisted.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "022_content_publish_attempts"
down_revision: str | None = "cef7acf8e4ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_publish_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=False),
        sa.Column("content_id", sa.String(length=256), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("live", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("provider_status", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("redacted_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(tenant_id)) > 0", name="ck_publish_attempt_tenant_nonempty"),
        sa.CheckConstraint("length(trim(provider)) > 0", name="ck_publish_attempt_provider_nonempty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "idempotency_key",
            name="uq_content_publish_attempts_idempotency",
        ),
    )
    op.create_index(
        "ix_content_publish_attempts_tenant_status",
        "content_publish_attempts",
        ["tenant_id", "provider_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_publish_attempts_tenant_status",
        table_name="content_publish_attempts",
    )
    op.drop_table("content_publish_attempts")
