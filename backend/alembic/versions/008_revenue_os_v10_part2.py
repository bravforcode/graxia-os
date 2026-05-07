"""Revenue OS v10 Part 2 - Leads, Campaigns, Content

Revision ID: 008_revenue_os_v10_part2
Revises: 007_revenue_os_v10
Create Date: 2026-04-26 00:01:00.000000

Description:
    Revenue OS v10 - Part 2
    - Lead management tables
    - Campaign & attribution tables
    - Content & approval tables
    - Email & delivery tables
    - Automation & incident tables
    - Metrics & analytics tables
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_revenue_os_v10_part2"
down_revision = "007_revenue_os_v10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create remaining Revenue OS tables"""

    # ══════════════════════════════════════════════════════════════════
    # LEAD MAGNETS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_lead_magnets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column(
            "target_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_products.id"),
        ),
        sa.Column("promise", sa.Text),
        sa.Column("file_url", sa.String(500)),
        sa.Column("landing_page_url", sa.String(500)),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("opt_in_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_lead_magnets_slug"),
    )

    # ══════════════════════════════════════════════════════════════════
    # LEADS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("source", sa.String(100)),
        sa.Column(
            "lead_magnet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_lead_magnets.id"),
        ),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("score_rationale", sa.Text),
        sa.Column("status", sa.String(50), nullable=False, server_default="new"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_leads_email"),
    )
    op.create_index("ix_leads_status", "revenue_os_leads", ["status"])
    op.create_index("ix_leads_score", "revenue_os_leads", ["score"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_leads_updated_at
        BEFORE UPDATE ON revenue_os_leads
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # CONTENT IDEAS & POSTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_content_ideas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False, server_default="tiktok"),
        sa.Column("hook", sa.Text),
        sa.Column("angle", sa.Text),
        sa.Column(
            "target_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_products.id"),
        ),
        sa.Column("score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="idea"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "revenue_os_content_posts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "content_idea_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_content_ideas.id"),
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("script", sa.Text),
        sa.Column("caption", sa.Text),
        sa.Column("cta", sa.Text),
        sa.Column("hashtags", sa.Text),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("post_url", sa.String(500)),
        sa.Column("views", sa.Integer, nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("leads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sales", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
    )

    # ══════════════════════════════════════════════════════════════════
    # LEAD EVENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_lead_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_leads.id", ondelete="CASCADE"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(255)),
        sa.Column("source", sa.String(100)),
        sa.Column(
            "content_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_content_posts.id"),
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_products.id")
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event", "email", "event_id", name="uq_lead_event_public_id"),
    )
    op.create_index(
        "ix_lead_events_lead_created", "revenue_os_lead_events", ["lead_id", "created_at"]
    )
    op.create_index("ix_lead_events_email_event", "revenue_os_lead_events", ["email", "event"])
    op.create_index("ix_lead_events_event_id", "revenue_os_lead_events", ["event_id"])

    # ══════════════════════════════════════════════════════════════════
    # CAMPAIGNS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_campaigns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_products.id")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("objective", sa.String(100), nullable=False, server_default="lead_to_sale"),
        sa.Column("target_audience", sa.Text),
        sa.Column("offer_angle", sa.Text),
        sa.Column("primary_cta", sa.Text),
        sa.Column("utm_source", sa.String(100)),
        sa.Column("utm_medium", sa.String(100)),
        sa.Column("utm_campaign", sa.String(150)),
        sa.Column("budget_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("spend_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("target_revenue_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actual_revenue_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("guardrails", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("paused_reason", sa.Text),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_revenue_campaign_slug"),
    )
    op.create_index("ix_campaign_status_product", "revenue_os_campaigns", ["status", "product_id"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_campaigns_updated_at
        BEFORE UPDATE ON revenue_os_campaigns
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # ENTITLEMENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_entitlements",
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
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("product_key", sa.String(255), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_entitlements_customer_email", "revenue_os_entitlements", ["customer_email"])
    op.create_index("ix_entitlements_product_key", "revenue_os_entitlements", ["product_key"])

    print("✓ Phase 1 Part 2: Lead, Campaign, Content tables created")


def downgrade() -> None:
    """Rollback Part 2 tables"""
    op.drop_table("revenue_os_entitlements")
    op.drop_table("revenue_os_campaigns")
    op.drop_table("revenue_os_lead_events")
    op.drop_table("revenue_os_content_posts")
    op.drop_table("revenue_os_content_ideas")
    op.drop_table("revenue_os_leads")
    op.drop_table("revenue_os_lead_magnets")
    print("✓ Phase 1 Part 2: Rolled back")
