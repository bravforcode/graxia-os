"""Revenue OS Improvements - Add Missing Constraints and Indexes

Revision ID: 010_revenue_os_improvements
Revises: 009_revenue_os_v10_part3
Create Date: 2026-04-26 12:00:00.000000

Description:
    Phase 1 & 2 Improvements:
    - Add missing CHECK constraints for data integrity
    - Add missing indexes for performance
    - Add missing unique constraints for idempotency
    - Add missing updated_at triggers
"""

from alembic import op

revision = "010_revenue_os_improvements"
down_revision = "009_revenue_os_v10_part3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing constraints, indexes, and triggers"""

    # ══════════════════════════════════════════════════════════════════
    # 1. ADD MISSING CHECK CONSTRAINTS
    # ══════════════════════════════════════════════════════════════════

    # Products: price_cents >= 0
    op.create_check_constraint(
        "ck_products_price_non_negative",
        "revenue_os_products",
        "price_cents IS NULL OR price_cents >= 0",
    )

    # Customers: total_spent_cents >= 0
    op.create_check_constraint(
        "ck_customers_total_spent_non_negative", "revenue_os_customers", "total_spent_cents >= 0"
    )

    # Campaigns: budget_cents >= 0
    op.create_check_constraint(
        "ck_campaigns_budget_non_negative", "revenue_os_campaigns", "budget_cents >= 0"
    )

    # Campaigns: spend_cents >= 0
    op.create_check_constraint(
        "ck_campaigns_spend_non_negative", "revenue_os_campaigns", "spend_cents >= 0"
    )

    # Campaigns: target_revenue_cents >= 0
    op.create_check_constraint(
        "ck_campaigns_target_revenue_non_negative",
        "revenue_os_campaigns",
        "target_revenue_cents >= 0",
    )

    # Campaigns: actual_revenue_cents >= 0
    op.create_check_constraint(
        "ck_campaigns_actual_revenue_non_negative",
        "revenue_os_campaigns",
        "actual_revenue_cents >= 0",
    )

    # Email Outbox: attempts >= 0
    op.create_check_constraint(
        "ck_email_outbox_attempts_non_negative", "revenue_os_email_outbox", "attempts >= 0"
    )

    # Email Outbox: retry_count >= 0
    op.create_check_constraint(
        "ck_email_outbox_retry_count_non_negative", "revenue_os_email_outbox", "retry_count >= 0"
    )

    # Refunds: amount_cents > 0
    op.create_check_constraint(
        "ck_refunds_amount_positive", "revenue_os_refunds", "amount_cents > 0"
    )

    # Lead Magnets: opt_in_count >= 0
    op.create_check_constraint(
        "ck_lead_magnets_opt_in_count_non_negative", "revenue_os_lead_magnets", "opt_in_count >= 0"
    )

    # Content Posts: metrics >= 0
    op.create_check_constraint(
        "ck_content_posts_views_non_negative", "revenue_os_content_posts", "views >= 0"
    )
    op.create_check_constraint(
        "ck_content_posts_likes_non_negative", "revenue_os_content_posts", "likes >= 0"
    )
    op.create_check_constraint(
        "ck_content_posts_comments_non_negative", "revenue_os_content_posts", "comments >= 0"
    )
    op.create_check_constraint(
        "ck_content_posts_clicks_non_negative", "revenue_os_content_posts", "clicks >= 0"
    )
    op.create_check_constraint(
        "ck_content_posts_leads_non_negative", "revenue_os_content_posts", "leads >= 0"
    )
    op.create_check_constraint(
        "ck_content_posts_sales_non_negative", "revenue_os_content_posts", "sales >= 0"
    )

    # ══════════════════════════════════════════════════════════════════
    # 2. ADD MISSING INDEXES FOR PERFORMANCE
    # ══════════════════════════════════════════════════════════════════

    # Email Outbox: (status, scheduled_at) for efficient pending email queries
    op.create_index(
        "ix_email_outbox_status_scheduled", "revenue_os_email_outbox", ["status", "scheduled_at"]
    )

    # Email Outbox: (status, attempts) for retry queries
    op.create_index(
        "ix_email_outbox_status_attempts", "revenue_os_email_outbox", ["status", "attempts"]
    )

    # Delivery Events: (status, created_at) for monitoring
    op.create_index(
        "ix_delivery_events_status_created", "revenue_os_delivery_events", ["status", "created_at"]
    )

    # Automation Runs: started_at for time-based queries
    op.create_index("ix_automation_runs_started_at", "revenue_os_automation_runs", ["started_at"])

    # Incident Events: (affected_campaign_id, status) for campaign monitoring
    op.create_index(
        "ix_incidents_campaign_status",
        "revenue_os_incident_events",
        ["affected_campaign_id", "status"],
    )

    # Approvals: (status, expires_at) for expiry checks
    op.create_index("ix_approvals_status_expires", "revenue_os_approvals", ["status", "expires_at"])

    # Orders: (customer_id, created_at) for customer order history
    op.create_index(
        "ix_orders_customer_created", "revenue_os_orders", ["customer_id", "created_at"]
    )

    # Leads: (status, score) for lead prioritization
    op.create_index("ix_leads_status_score", "revenue_os_leads", ["status", "score"])

    # ══════════════════════════════════════════════════════════════════
    # 3. ADD MISSING UNIQUE CONSTRAINTS FOR IDEMPOTENCY
    # ══════════════════════════════════════════════════════════════════

    # Strategy Logs: unique week_start to prevent duplicate weekly reviews
    op.create_unique_constraint(
        "uq_strategy_logs_week_start", "revenue_os_strategy_logs", ["week_start"]
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. ADD MISSING UPDATED_AT TRIGGERS
    # ══════════════════════════════════════════════════════════════════

    # Lead Magnets
    op.execute("""
        CREATE TRIGGER set_revenue_os_lead_magnets_updated_at
        BEFORE UPDATE ON revenue_os_lead_magnets
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Content Ideas
    op.execute("""
        CREATE TRIGGER set_revenue_os_content_ideas_updated_at
        BEFORE UPDATE ON revenue_os_content_ideas
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Content Posts
    op.execute("""
        CREATE TRIGGER set_revenue_os_content_posts_updated_at
        BEFORE UPDATE ON revenue_os_content_posts
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Approvals
    op.execute("""
        CREATE TRIGGER set_revenue_os_approvals_updated_at
        BEFORE UPDATE ON revenue_os_approvals
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # AI Drafts
    op.execute("""
        CREATE TRIGGER set_revenue_os_ai_drafts_updated_at
        BEFORE UPDATE ON revenue_os_ai_drafts
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Email Outbox
    op.execute("""
        CREATE TRIGGER set_revenue_os_email_outbox_updated_at
        BEFORE UPDATE ON revenue_os_email_outbox
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Automation Runs
    op.execute("""
        CREATE TRIGGER set_revenue_os_automation_runs_updated_at
        BEFORE UPDATE ON revenue_os_automation_runs
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Incident Events
    op.execute("""
        CREATE TRIGGER set_revenue_os_incident_events_updated_at
        BEFORE UPDATE ON revenue_os_incident_events
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Webhook Events
    op.execute("""
        CREATE TRIGGER set_revenue_os_webhook_events_updated_at
        BEFORE UPDATE ON revenue_os_webhook_events
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    # Tasks
    op.execute("""
        CREATE TRIGGER set_revenue_os_tasks_updated_at
        BEFORE UPDATE ON revenue_os_tasks
        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    """)

    print("✓ Revenue OS Improvements: All constraints, indexes, and triggers added")
    print("✓ Data integrity: Enhanced with CHECK constraints")
    print("✓ Performance: Optimized with composite indexes")
    print("✓ Idempotency: Protected with unique constraints")
    print("✓ Audit trail: Complete with updated_at triggers")


def downgrade() -> None:
    """Remove improvements"""

    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS set_revenue_os_tasks_updated_at ON revenue_os_tasks")
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_webhook_events_updated_at ON revenue_os_webhook_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_incident_events_updated_at ON revenue_os_incident_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_automation_runs_updated_at ON revenue_os_automation_runs"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_email_outbox_updated_at ON revenue_os_email_outbox"
    )
    op.execute("DROP TRIGGER IF EXISTS set_revenue_os_ai_drafts_updated_at ON revenue_os_ai_drafts")
    op.execute("DROP TRIGGER IF EXISTS set_revenue_os_approvals_updated_at ON revenue_os_approvals")
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_content_posts_updated_at ON revenue_os_content_posts"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_content_ideas_updated_at ON revenue_os_content_ideas"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS set_revenue_os_lead_magnets_updated_at ON revenue_os_lead_magnets"
    )

    # Drop unique constraints
    op.drop_constraint("uq_strategy_logs_week_start", "revenue_os_strategy_logs")

    # Drop indexes
    op.drop_index("ix_leads_status_score", "revenue_os_leads")
    op.drop_index("ix_orders_customer_created", "revenue_os_orders")
    op.drop_index("ix_approvals_status_expires", "revenue_os_approvals")
    op.drop_index("ix_incidents_campaign_status", "revenue_os_incident_events")
    op.drop_index("ix_automation_runs_started_at", "revenue_os_automation_runs")
    op.drop_index("ix_delivery_events_status_created", "revenue_os_delivery_events")
    op.drop_index("ix_email_outbox_status_attempts", "revenue_os_email_outbox")
    op.drop_index("ix_email_outbox_status_scheduled", "revenue_os_email_outbox")

    # Drop check constraints
    op.drop_constraint("ck_content_posts_sales_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_content_posts_leads_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_content_posts_clicks_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_content_posts_comments_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_content_posts_likes_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_content_posts_views_non_negative", "revenue_os_content_posts")
    op.drop_constraint("ck_lead_magnets_opt_in_count_non_negative", "revenue_os_lead_magnets")
    op.drop_constraint("ck_refunds_amount_positive", "revenue_os_refunds")
    op.drop_constraint("ck_email_outbox_retry_count_non_negative", "revenue_os_email_outbox")
    op.drop_constraint("ck_email_outbox_attempts_non_negative", "revenue_os_email_outbox")
    op.drop_constraint("ck_campaigns_actual_revenue_non_negative", "revenue_os_campaigns")
    op.drop_constraint("ck_campaigns_target_revenue_non_negative", "revenue_os_campaigns")
    op.drop_constraint("ck_campaigns_spend_non_negative", "revenue_os_campaigns")
    op.drop_constraint("ck_campaigns_budget_non_negative", "revenue_os_campaigns")
    op.drop_constraint("ck_customers_total_spent_non_negative", "revenue_os_customers")
    op.drop_constraint("ck_products_price_non_negative", "revenue_os_products")

    print("✓ Revenue OS Improvements: Rolled back")
