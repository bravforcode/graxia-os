"""Revenue OS v10 Enterprise Integration

Revision ID: 007_revenue_os_v10
Revises: 006_revenue_os_round3_fixes
Create Date: 2026-04-26 00:00:00.000000

Description:
    Integrate Absolute Revenue OS v10 into Graxia OS
    - All 20+ Revenue OS models
    - Idempotency constraints
    - RLS policies
    - Updated_at triggers
    - Performance indexes
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_revenue_os_v10"
down_revision = "89d09d4d6b03"  # Latest migration (performance indexes)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Phase 1: Enterprise Data Layer & Schema Merging
    All tables use revenue_os_ prefix to avoid conflicts
    """

    # ══════════════════════════════════════════════════════════════════
    # Extensions
    # ══════════════════════════════════════════════════════════════════
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')

    # ══════════════════════════════════════════════════════════════════
    # Trigger Function for updated_at
    # ══════════════════════════════════════════════════════════════════
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ══════════════════════════════════════════════════════════════════
    # PRODUCTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_products",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False, server_default="low_ticket"),
        sa.Column("price_cents", sa.Integer),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("status", sa.String(50), nullable=False, server_default="idea"),
        sa.Column("promise", sa.Text),
        sa.Column("target_audience", sa.Text),
        sa.Column("pain_points", sa.Text),
        sa.Column("deliverables", sa.Text),
        sa.Column("stripe_price_id", sa.String(255)),
        sa.Column("stripe_payment_link_url", sa.String(500)),
        sa.Column("gumroad_url", sa.String(500)),
        sa.Column("fulfillment_url", sa.String(1000)),
        sa.Column("fulfillment_instructions", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_status", "revenue_os_products", ["status"])
    op.create_index("ix_products_type", "revenue_os_products", ["type"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_products_updated_at
        BEFORE UPDATE ON revenue_os_products
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # CUSTOMERS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_customers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("stripe_customer_id", sa.String(255)),
        sa.Column("total_spent_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_purchase_at", sa.DateTime(timezone=True)),
        sa.Column("last_purchase_at", sa.DateTime(timezone=True)),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_customers_email"),
    )
    op.create_index("ix_customers_stripe_id", "revenue_os_customers", ["stripe_customer_id"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_customers_updated_at
        BEFORE UPDATE ON revenue_os_customers
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # ORDERS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_order_id", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column(
            "customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_customers.id")
        ),
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("customer_name", sa.String(255)),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_products.id"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("delivery_status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("stripe_payment_intent", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("notes", sa.Text),
        sa.Column("purchased_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_order_id", name="uq_orders_platform_order"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        sa.CheckConstraint("amount_cents > 0", name="ck_orders_amount_positive"),
    )
    op.create_index("ix_orders_customer_email", "revenue_os_orders", ["customer_email"])
    op.create_index("ix_orders_status", "revenue_os_orders", ["status"])
    op.create_index("ix_orders_created_at", "revenue_os_orders", ["created_at"])
    op.create_index("ix_orders_product_status", "revenue_os_orders", ["product_id", "status"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_orders_updated_at
        BEFORE UPDATE ON revenue_os_orders
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # LEDGER ENTRIES (Append-only)
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_orders.id"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("description", sa.Text),
        sa.Column("stripe_balance_transaction_id", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("amount_cents != 0", name="ck_ledger_nonzero"),
    )
    op.create_index("ix_ledger_order_id", "revenue_os_ledger_entries", ["order_id"])
    op.create_index("ix_ledger_entry_type", "revenue_os_ledger_entries", ["entry_type"])
    op.create_index("ix_ledger_created_at", "revenue_os_ledger_entries", ["created_at"])

    # ══════════════════════════════════════════════════════════════════
    # REFUNDS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_refunds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_orders.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_customers.id")
        ),
        sa.Column("platform", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("platform_refund_id", sa.String(255)),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="THB"),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(50), nullable=False, server_default="succeeded"),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_refund_id", name="uq_refund_platform_refund_id"),
    )
    op.create_index("ix_refunds_order_id", "revenue_os_refunds", ["order_id"])
    op.create_index("ix_refund_order_status", "revenue_os_refunds", ["order_id", "status"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_refunds_updated_at
        BEFORE UPDATE ON revenue_os_refunds
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Continue with remaining tables in next part...
    print("✓ Phase 1 Migration: Core financial tables created")


def downgrade() -> None:
    """
    Rollback Revenue OS v10 integration
    """
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table("revenue_os_refunds")
    op.drop_table("revenue_os_ledger_entries")
    op.drop_table("revenue_os_orders")
    op.drop_table("revenue_os_customers")
    op.drop_table("revenue_os_products")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS trigger_set_updated_at CASCADE")

    print("✓ Phase 1 Migration: Rolled back")
