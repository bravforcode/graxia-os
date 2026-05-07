"""Revenue OS v10 Part 3 - Automation, Email, Metrics

Revision ID: 009_revenue_os_v10_part3
Revises: 008_revenue_os_v10_part2
Create Date: 2026-04-26 00:02:00.000000

Description:
    Revenue OS v10 - Part 3 (Final)
    - Approval & AI Draft tables
    - Email & Delivery tables
    - Automation & Incident tables
    - Attribution & Experiment tables
    - Metrics & Analytics tables
    - Webhook & Audit tables
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_revenue_os_v10_part3"
down_revision = "008_revenue_os_v10_part2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create final Revenue OS tables"""

    # ══════════════════════════════════════════════════════════════════
    # AI DRAFTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_ai_drafts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("draft_type", sa.String(100), nullable=False),
        sa.Column("object_type", sa.String(100)),
        sa.Column("object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_leads.id")),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column("prompt_summary", sa.Text),
        sa.Column("output", sa.Text, nullable=False),
        sa.Column("subject", sa.String(998)),
        sa.Column("model_used", sa.String(100)),
        sa.Column("anthropic_model", sa.String(100)),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column(
            "approval_status", sa.String(50), nullable=False, server_default="pending_approval"
        ),
        sa.Column("generated_by_agent", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ══════════════════════════════════════════════════════════════════
    # APPROVALS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_products.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "content_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_content_posts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "ai_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_ai_drafts.id", ondelete="SET NULL"),
        ),
        sa.Column("title", sa.String(255)),
        sa.Column("preview", sa.Text),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_approval"),
        sa.Column("requested_by_agent", sa.String(100)),
        sa.Column("ceo_notes", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_approvals_status", "revenue_os_approvals", ["status"])
    op.create_index(
        "ix_approvals_item_type_id", "revenue_os_approvals", ["object_type", "object_id"]
    )

    # Update AI drafts to reference approvals
    op.add_column(
        "revenue_os_ai_drafts",
        sa.Column(
            "approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_approvals.id")
        ),
    )

    # ══════════════════════════════════════════════════════════════════
    # EMAIL OUTBOX
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_email_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_orders.id")),
        sa.Column(
            "customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_customers.id")
        ),
        sa.Column("email_key", sa.String(255)),
        sa.Column("to_email", sa.String(255), nullable=False),
        sa.Column("to_name", sa.String(255)),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("html_body", sa.Text),
        sa.Column("text_body", sa.Text),
        sa.Column("from_email", sa.String(320)),
        sa.Column("reply_to", sa.String(320)),
        sa.Column(
            "approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_approvals.id")
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("resend_message_id", sa.String(255)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email_key", name="uq_email_outbox_email_key"),
    )
    op.create_index("ix_email_outbox_status", "revenue_os_email_outbox", ["status"])

    # ══════════════════════════════════════════════════════════════════
    # DELIVERY EVENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_delivery_events",
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
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("delivery_type", sa.String(100)),
        sa.Column("channel", sa.String(50), nullable=False, server_default="delivery_page"),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column(
            "email_outbox_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_email_outbox.id"),
        ),
        sa.Column("message", sa.Text),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_delivery_order_type", "revenue_os_delivery_events", ["order_id", "event_type"]
    )
    op.execute("""
        CREATE TRIGGER set_revenue_os_delivery_events_updated_at
        BEFORE UPDATE ON revenue_os_delivery_events
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # AUTOMATION LOCKS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_automation_locks",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("locked_by_worker", sa.String(255)),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_locks_expires_at", "revenue_os_automation_locks", ["locked_until"])
    op.execute("""
        CREATE TRIGGER set_revenue_os_automation_locks_updated_at
        BEFORE UPDATE ON revenue_os_automation_locks
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # AUTOMATION RUNS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_automation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("summary", sa.Text),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_automation_run_type_status", "revenue_os_automation_runs", ["run_type", "status"]
    )

    # ══════════════════════════════════════════════════════════════════
    # INCIDENT EVENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_incident_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("severity", sa.String(50), nullable=False, server_default="warning"),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("source_agent", sa.String(100)),
        sa.Column("source", sa.String(100)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("message", sa.Text),
        sa.Column(
            "affected_campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_campaigns.id"),
        ),
        sa.Column(
            "affected_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_orders.id"),
        ),
        sa.Column("bwcp_message_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_incidents_severity", "revenue_os_incident_events", ["severity"])
    op.create_index("ix_incidents_created_at", "revenue_os_incident_events", ["created_at"])
    op.create_index(
        "ix_incident_status_severity", "revenue_os_incident_events", ["status", "severity"]
    )

    # ══════════════════════════════════════════════════════════════════
    # ATTRIBUTION EVENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_attribution_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_products.id")
        ),
        sa.Column(
            "content_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_content_posts.id"),
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_leads.id")),
        sa.Column(
            "customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_customers.id")
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_orders.id")),
        sa.Column("source", sa.String(100)),
        sa.Column("medium", sa.String(100)),
        sa.Column("campaign", sa.String(150)),
        sa.Column("value_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", name="uq_attribution_event_id"),
    )
    op.create_index(
        "ix_attribution_campaign_event",
        "revenue_os_attribution_events",
        ["campaign_id", "event_type"],
    )
    op.create_index(
        "ix_attribution_source_created", "revenue_os_attribution_events", ["source", "created_at"]
    )

    # ══════════════════════════════════════════════════════════════════
    # REVENUE EXPERIMENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_experiments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_products.id")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hypothesis", sa.Text, nullable=False),
        sa.Column("variant_a", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("variant_b", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "success_metric", sa.String(100), nullable=False, server_default="paid_conversion_rate"
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("result", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_experiment_campaign_status", "revenue_os_experiments", ["campaign_id", "status"]
    )
    op.execute("""
        CREATE TRIGGER set_revenue_os_experiments_updated_at
        BEFORE UPDATE ON revenue_os_experiments
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # ══════════════════════════════════════════════════════════════════
    # WEBHOOK EVENTS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("platform", sa.String(50)),
        sa.Column("platform_event_id", sa.String(255)),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(255)),
        sa.Column("status", sa.String(50), nullable=False, server_default="received"),
        sa.Column("processed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("processing_error", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        sa.UniqueConstraint("platform", "platform_event_id", name="uq_webhook_platform_event"),
    )
    op.create_index("ix_webhook_events_processed", "revenue_os_webhook_events", ["processed"])
    op.create_index(
        "ix_webhook_events_platform_event", "revenue_os_webhook_events", ["platform", "event_type"]
    )

    # ══════════════════════════════════════════════════════════════════
    # METRICS & ANALYTICS
    # ══════════════════════════════════════════════════════════════════
    op.create_table(
        "revenue_os_metrics_daily",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("visits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("leads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sales", sa.Integer, nullable=False, server_default="0"),
        sa.Column("revenue_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_published", sa.Integer, nullable=False, server_default="0"),
        sa.Column("email_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("service_inquiries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversion_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("date", name="uq_metrics_daily_date"),
    )
    op.execute("""
        CREATE TRIGGER set_revenue_os_metrics_daily_updated_at
        BEFORE UPDATE ON revenue_os_metrics_daily
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    op.create_table(
        "revenue_os_strategy_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("what_worked", sa.Text),
        sa.Column("what_failed", sa.Text),
        sa.Column("recommendations", sa.Text),
        sa.Column("top_3_actions", sa.Text),
        sa.Column("kill_list", sa.Text),
        sa.Column("double_down_list", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "revenue_os_audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("object_type", sa.String(100)),
        sa.Column("object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "revenue_os_service_offers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("price_min_cents", sa.Integer),
        sa.Column("price_max_cents", sa.Integer),
        sa.Column("promise", sa.Text),
        sa.Column("deliverables", sa.Text),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("""
        CREATE TRIGGER set_revenue_os_service_offers_updated_at
        BEFORE UPDATE ON revenue_os_service_offers
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    op.create_table(
        "revenue_os_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("priority", sa.Integer, nullable=False, server_default="50"),
        sa.Column("category", sa.String(100)),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("due_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    print("✓ Phase 1 Part 3: All Revenue OS tables created successfully!")
    print("✓ Total tables: 30+")
    print("✓ Ready for Phase 2: Core Business Logic & Celery Automation")


def downgrade() -> None:
    """Rollback Part 3 tables"""
    op.drop_table("revenue_os_tasks")
    op.drop_table("revenue_os_service_offers")
    op.drop_table("revenue_os_audit_logs")
    op.drop_table("revenue_os_strategy_logs")
    op.drop_table("revenue_os_metrics_daily")
    op.drop_table("revenue_os_webhook_events")
    op.drop_table("revenue_os_experiments")
    op.drop_table("revenue_os_attribution_events")
    op.drop_table("revenue_os_incident_events")
    op.drop_table("revenue_os_automation_runs")
    op.drop_table("revenue_os_automation_locks")
    op.drop_table("revenue_os_delivery_events")
    op.drop_table("revenue_os_email_outbox")
    op.drop_table("revenue_os_approvals")
    op.drop_table("revenue_os_ai_drafts")
    print("✓ Phase 1 Part 3: Rolled back")
