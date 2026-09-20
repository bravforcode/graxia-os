"""add tenant-scoped organic content batches and idempotent items."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "027_content_batches"
down_revision: str | Sequence[str] | None = "026_revenue_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("site", sa.String(length=20), nullable=False, server_default="site_a"),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="organic"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("live", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("claim_ids", postgresql.JSONB(), nullable=True),
        sa.Column("canary_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "provider_credentials_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=255), nullable=True),
        sa.Column("block_codes", postgresql.JSONB(), nullable=True),
        sa.Column("export_manifest", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["approval_requests.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_content_batches_org_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('queued','processing','exported','published','blocked','failed')",
            name="ck_content_batch_status",
        ),
        sa.CheckConstraint("site IN ('site_a','site_b')", name="ck_content_batch_site"),
        sa.CheckConstraint("language IN ('en','th')", name="ck_content_batch_language"),
        sa.CheckConstraint(
            "item_count >= 0 AND item_count <= 9",
            name="ck_content_batch_item_count",
        ),
    )
    op.create_index(
        "ix_content_batches_org_status",
        "content_batches",
        ["organization_id", "status"],
    )

    op.create_table(
        "content_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("utm_params", postgresql.JSONB(), nullable=True),
        sa.Column("claim_ids", postgresql.JSONB(), nullable=True),
        sa.Column("article_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider_status", sa.String(length=64), nullable=True),
        sa.Column("publish_receipt", postgresql.JSONB(), nullable=True),
        sa.Column("block_codes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["content_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["content_articles.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("batch_id", "item_key", name="uq_content_batch_items_key"),
        sa.UniqueConstraint(
            "batch_id",
            "idempotency_key",
            name="uq_content_batch_items_idempotency",
        ),
        sa.CheckConstraint(
            "role IN ('pillar','supporting','short')",
            name="ck_content_batch_item_role",
        ),
        sa.CheckConstraint(
            "status IN ('draft','dry_run','blocked','published','failed')",
            name="ck_content_batch_item_status",
        ),
    )
    op.create_index(
        "ix_content_batch_items_batch_status",
        "content_batch_items",
        ["batch_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_batch_items_batch_status", table_name="content_batch_items")
    op.drop_table("content_batch_items")
    op.drop_index("ix_content_batches_org_status", table_name="content_batches")
    op.drop_table("content_batches")
