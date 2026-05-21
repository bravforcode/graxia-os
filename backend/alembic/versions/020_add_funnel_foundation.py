"""add funnel foundation models

Revision ID: 020_add_funnel_foundation
Revises: 019_content_engine
Create Date: 2026-05-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "020_add_funnel_foundation"
down_revision: str | None = "019_content_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Create digital_products ──────────────────────────────────────────
    op.create_table(
        "digital_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("product_type", sa.String(length=50), nullable=False, server_default="other"),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="THB"),
        sa.Column("stripe_price_id", sa.String(length=100), nullable=True),
        sa.Column("stripe_product_id", sa.String(length=100), nullable=True),
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        sa.Column("sales_page_content", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_product_status"),
        sa.CheckConstraint("product_type IN ('ebook', 'template', 'prompt_pack', 'course', 'kit', 'other')", name="ck_product_type"),
        sa.CheckConstraint("price_amount >= 0", name="ck_product_price_non_negative"),
    )
    op.create_index("ix_digital_products_org_slug", "digital_products", ["organization_id", "slug"], unique=True)
    op.create_index(op.f("ix_digital_products_organization_id"), "digital_products", ["organization_id"], unique=False)

    # ── 2. Create delivery_assets ───────────────────────────────────────────
    op.create_table(
        "delivery_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("content_body", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("asset_type IN ('file', 'external_link', 'text', 'private_page')", name="ck_asset_type"),
    )
    op.create_index(op.f("ix_delivery_assets_organization_id"), "delivery_assets", ["organization_id"], unique=False)
    op.create_index(op.f("ix_delivery_assets_product_id"), "delivery_assets", ["product_id"], unique=False)

    # ── 3. Create funnel_checkout_sessions ────────────────────────────────────────
    op.create_table(
        "funnel_checkout_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="created"),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="THB"),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('created', 'pending', 'completed', 'expired', 'failed', 'cancelled')", name="ck_checkout_status"),
    )
    op.create_index(op.f("ix_funnel_checkout_sessions_contact_id"), "funnel_checkout_sessions", ["contact_id"], unique=False)
    op.create_index(op.f("ix_funnel_checkout_sessions_organization_id"), "funnel_checkout_sessions", ["organization_id"], unique=False)
    op.create_index(op.f("ix_funnel_checkout_sessions_product_id"), "funnel_checkout_sessions", ["product_id"], unique=False)
    op.create_index(op.f("ix_funnel_checkout_sessions_stripe_session_id"), "funnel_checkout_sessions", ["stripe_session_id"], unique=True)
    op.create_index(op.f("ix_funnel_checkout_sessions_user_id"), "funnel_checkout_sessions", ["user_id"], unique=False)

    # ── 4. Create funnel_orders ───────────────────────────────────────────────────
    op.create_table(
        "funnel_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checkout_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("subtotal_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="THB"),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["checkout_session_id"], ["funnel_checkout_sessions.id"], ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('pending', 'paid', 'failed', 'refunded', 'cancelled')", name="ck_order_status"),
    )
    op.create_index(op.f("ix_funnel_orders_checkout_session_id"), "funnel_orders", ["checkout_session_id"], unique=False)
    op.create_index(op.f("ix_funnel_orders_contact_id"), "funnel_orders", ["contact_id"], unique=False)
    op.create_index(op.f("ix_funnel_orders_organization_id"), "funnel_orders", ["organization_id"], unique=False)
    op.create_index(op.f("ix_funnel_orders_stripe_payment_intent_id"), "funnel_orders", ["stripe_payment_intent_id"], unique=False)
    op.create_index(op.f("ix_funnel_orders_stripe_session_id"), "funnel_orders", ["stripe_session_id"], unique=False)
    op.create_index(op.f("ix_funnel_orders_user_id"), "funnel_orders", ["user_id"], unique=False)

    # ── 5. Create funnel_order_items ──────────────────────────────────────────────
    op.create_table(
        "funnel_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="THB"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["funnel_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity >= 1", name="ck_order_item_quantity_positive"),
    )
    op.create_index(op.f("ix_funnel_order_items_order_id"), "funnel_order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_funnel_order_items_organization_id"), "funnel_order_items", ["organization_id"], unique=False)
    op.create_index(op.f("ix_funnel_order_items_product_id"), "funnel_order_items", ["product_id"], unique=False)

    # ── 6. Create delivery_accesses ─────────────────────────────────────────
    op.create_table(
        "delivery_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("access_token_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_downloads", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["delivery_assets.id"], ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ),
        sa.ForeignKeyConstraint(["order_id"], ["funnel_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name="ck_delivery_access_status"),
    )
    op.create_index(op.f("ix_delivery_accesses_access_token_hash"), "delivery_accesses", ["access_token_hash"], unique=False)
    op.create_index(op.f("ix_delivery_accesses_asset_id"), "delivery_accesses", ["asset_id"], unique=False)
    op.create_index(op.f("ix_delivery_accesses_contact_id"), "delivery_accesses", ["contact_id"], unique=False)
    op.create_index(op.f("ix_delivery_accesses_order_id"), "delivery_accesses", ["order_id"], unique=False)
    op.create_index(op.f("ix_delivery_accesses_organization_id"), "delivery_accesses", ["organization_id"], unique=False)
    op.create_index(op.f("ix_delivery_accesses_product_id"), "delivery_accesses", ["product_id"], unique=False)

    # ── 7. Create conversion_events ─────────────────────────────────────────
    op.create_table(
        "conversion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("medium", sa.String(length=100), nullable=True),
        sa.Column("campaign", sa.String(length=100), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ),
        sa.ForeignKeyConstraint(["order_id"], ["funnel_orders.id"], ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("event_type IN ('page_view', 'lead_capture', 'checkout_start', 'checkout_success', 'purchase', 'delivery_opened')", name="ck_conversion_event_type"),
    )
    op.create_index(op.f("ix_conversion_events_contact_id"), "conversion_events", ["contact_id"], unique=False)
    op.create_index(op.f("ix_conversion_events_event_type"), "conversion_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_conversion_events_occurred_at"), "conversion_events", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_conversion_events_order_id"), "conversion_events", ["order_id"], unique=False)
    op.create_index(op.f("ix_conversion_events_organization_id"), "conversion_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_conversion_events_product_id"), "conversion_events", ["product_id"], unique=False)
    op.create_index(op.f("ix_conversion_events_session_id"), "conversion_events", ["session_id"], unique=False)
    op.create_index("ix_conversion_events_org_type_occurred", "conversion_events", ["organization_id", "event_type", "occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_table("conversion_events")
    op.drop_table("delivery_accesses")
    op.drop_table("funnel_order_items")
    op.drop_table("funnel_orders")
    op.drop_table("funnel_checkout_sessions")
    op.drop_table("delivery_assets")
    op.drop_table("digital_products")
