"""add funnel V5 models — delivery email events, lead magnets, captures, recommendations, delivery access V5 fields

Revision ID: 021_add_funnel_v5_models
Revises: 1e9db9a3b0ba
Create Date: 2026-05-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "021_add_funnel_v5_models"
down_revision: str | None = "1e9db9a3b0ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Add V5 columns to delivery_accesses ──────────────────────────────
    op.add_column(
        "delivery_accesses",
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "delivery_accesses",
        sa.Column("delivery_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "delivery_accesses",
        sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "delivery_accesses",
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "delivery_accesses",
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "delivery_accesses",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Add FK constraints for new columns
    op.create_foreign_key(
        "fk_delivery_accesses_order_item_id",
        "delivery_accesses", "funnel_order_items",
        ["order_item_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_delivery_accesses_delivery_asset_id",
        "delivery_accesses", "delivery_assets",
        ["delivery_asset_id"], ["id"],
    )

    # Create index for new columns
    op.create_index(
        op.f("ix_delivery_accesses_order_item_id"),
        "delivery_accesses", ["order_item_id"], unique=False,
    )
    op.create_index(
        op.f("ix_delivery_accesses_delivery_asset_id"),
        "delivery_accesses", ["delivery_asset_id"], unique=False,
    )

    # Make access_token_hash unique (drop old non-unique, create unique)
    op.drop_index(
        op.f("ix_delivery_accesses_access_token_hash"),
        table_name="delivery_accesses",
    )
    op.create_index(
        "ix_delivery_access_token_hash",
        "delivery_accesses", ["access_token_hash"], unique=True,
        postgresql_where=sa.text("access_token_hash IS NOT NULL"),
    )

    # ── 2. Create delivery_email_events ──────────────────────────────────────
    op.create_table(
        "delivery_email_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_access_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=100), nullable=False, server_default="mock"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message_redacted", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["funnel_orders.id"]),
        sa.ForeignKeyConstraint(["delivery_access_id"], ["delivery_accesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_delivery_email_status",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_delivery_email_idempotency"),
    )
    op.create_index(
        op.f("ix_delivery_email_events_organization_id"),
        "delivery_email_events", ["organization_id"], unique=False,
    )
    op.create_index(
        op.f("ix_delivery_email_events_order_id"),
        "delivery_email_events", ["order_id"], unique=False,
    )
    op.create_index(
        op.f("ix_delivery_email_events_delivery_access_id"),
        "delivery_email_events", ["delivery_access_id"], unique=False,
    )

    # ── 3. Create lead_magnets ──────────────────────────────────────────────
    op.create_table(
        "lead_magnets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["delivery_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_lead_magnet_status",
        ),
    )
    op.create_index(
        "ix_lead_magnet_org_slug",
        "lead_magnets", ["organization_id", "slug"], unique=True,
    )
    op.create_index(
        op.f("ix_lead_magnets_organization_id"),
        "lead_magnets", ["organization_id"], unique=False,
    )
    op.create_index(
        op.f("ix_lead_magnets_product_id"),
        "lead_magnets", ["product_id"], unique=False,
    )
    op.create_index(
        op.f("ix_lead_magnets_asset_id"),
        "lead_magnets", ["asset_id"], unique=False,
    )

    # ── 4. Create lead_captures ──────────────────────────────────────────────
    op.create_table(
        "lead_captures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_magnet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("utm_source", sa.String(length=255), nullable=True),
        sa.Column("utm_medium", sa.String(length=255), nullable=True),
        sa.Column("utm_campaign", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_magnet_id"], ["lead_magnets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_capture_org_magnet_email",
        "lead_captures", ["organization_id", "lead_magnet_id", "email"], unique=True,
    )
    op.create_index(
        op.f("ix_lead_captures_organization_id"),
        "lead_captures", ["organization_id"], unique=False,
    )
    op.create_index(
        op.f("ix_lead_captures_lead_magnet_id"),
        "lead_captures", ["lead_magnet_id"], unique=False,
    )

    # ── 5. Create funnel_recommendations ─────────────────────────────────────
    op.create_table(
        "funnel_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_type", sa.String(length=50), nullable=False),
        sa.Column("bottleneck", sa.String(length=255), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("expected_impact", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.String(length=50), nullable=True),
        sa.Column("effort", sa.String(length=50), nullable=True),
        sa.Column("risk", sa.String(length=50), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("draft_content", sa.Text(), nullable=True),
        sa.Column("rollback_note", sa.Text(), nullable=True),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'rejected', 'archived')",
            name="ck_recommendation_status",
        ),
    )
    op.create_index(
        op.f("ix_funnel_recommendations_organization_id"),
        "funnel_recommendations", ["organization_id"], unique=False,
    )
    op.create_index(
        op.f("ix_funnel_recommendations_product_id"),
        "funnel_recommendations", ["product_id"], unique=False,
    )
    op.create_index(
        op.f("ix_funnel_recommendations_approval_request_id"),
        "funnel_recommendations", ["approval_request_id"], unique=False,
    )


def downgrade() -> None:
    # Drop funnel_recommendations
    op.drop_table("funnel_recommendations")
    # Drop lead_captures
    op.drop_table("lead_captures")
    # Drop lead_magnets
    op.drop_table("lead_magnets")
    # Drop delivery_email_events
    op.drop_table("delivery_email_events")

    # Remove V5 columns from delivery_accesses
    op.drop_index("ix_delivery_access_token_hash", table_name="delivery_accesses")
    op.create_index(
        op.f("ix_delivery_accesses_access_token_hash"),
        "delivery_accesses", ["access_token_hash"], unique=False,
    )
    op.drop_index(op.f("ix_delivery_accesses_order_item_id"), table_name="delivery_accesses")
    op.drop_index(op.f("ix_delivery_accesses_delivery_asset_id"), table_name="delivery_accesses")
    op.drop_constraint("fk_delivery_accesses_order_item_id", "delivery_accesses", type_="foreignkey")
    op.drop_constraint("fk_delivery_accesses_delivery_asset_id", "delivery_accesses", type_="foreignkey")
    op.drop_column("delivery_accesses", "order_item_id")
    op.drop_column("delivery_accesses", "delivery_asset_id")
    op.drop_column("delivery_accesses", "first_opened_at")
    op.drop_column("delivery_accesses", "last_opened_at")
    op.drop_column("delivery_accesses", "open_count")
    op.drop_column("delivery_accesses", "metadata_json")
