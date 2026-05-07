"""
Revenue OS v12 Data Layer Migration

Adds complete v12 schema:
- OutboxEvent (transactional outbox pattern)
- BWCPMessage (agent messaging)
- LeadScoreHistory (immutable scoring history)
- PromptVersion (versioned AI prompts)
- CampaignBudgetSnapshot (budget analytics)
- AttributionSummary (pre-computed attribution)

Updates existing enums to v12 specification.
Adds saga_state to Order.

Revision ID: 012_revenue_os_v12
Revises: 011_add_missing_updated_at_columns
Create Date: 2026-01-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "012_revenue_os_v12"
down_revision: str | None = "011_add_missing_updated_at_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Acquire advisory lock to prevent concurrent migrations
    op.execute("SELECT pg_advisory_lock(123456789)")

    # Create enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE agenttype AS ENUM (
                'VisionaryAgent', 'SalesAgent', 'ChiefOfStaffAgent', 'ResearchAgent', 'system'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE bwcpmessagetype AS ENUM (
                'campaign_created', 'campaign_paused', 'campaign_resumed', 'campaign_target_hit',
                'lead_identified', 'lead_scored', 'lead_converted',
                'draft_queued', 'approval_required', 'approval_approved', 'approval_rejected',
                'approval_expired', 'incident_created', 'incident_resolved',
                'order_fulfilled', 'order_refunded'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create OutboxEvent table (transactional outbox)
    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("headers", postgresql.JSONB),
        sa.Column("correlation_id", sa.String(255)),
        sa.Column("causation_id", sa.String(255)),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_outbox_processed_at", "outbox_events", ["processed_at"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])

    # Create BWCPMessage table (agent messaging)
    op.create_table(
        "bwcp_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("conversation_id", sa.String(255), nullable=False),
        sa.Column(
            "sender_agent",
            postgresql.ENUM(
                "VisionaryAgent",
                "SalesAgent",
                "ChiefOfStaffAgent",
                "ResearchAgent",
                "system",
                name="agenttype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "recipient_agent",
            postgresql.ENUM(
                "VisionaryAgent",
                "SalesAgent",
                "ChiefOfStaffAgent",
                "ResearchAgent",
                "system",
                name="agenttype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "message_type",
            postgresql.ENUM(
                "campaign_created",
                "campaign_paused",
                "campaign_resumed",
                "campaign_target_hit",
                "lead_identified",
                "lead_scored",
                "lead_converted",
                "draft_queued",
                "approval_required",
                "approval_approved",
                "approval_rejected",
                "approval_expired",
                "incident_created",
                "incident_resolved",
                "order_fulfilled",
                "order_refunded",
                name="bwcpmessagetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("belief", sa.Text()),
        sa.Column("will", sa.Text()),
        sa.Column("can", postgresql.JSONB),
        sa.Column("plan", postgresql.JSONB),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_leads.id")),
        sa.Column(
            "approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_approvals.id")
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_incident_events.id"),
        ),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_bwcp_conversation", "bwcp_messages", ["conversation_id", "created_at"])
    op.create_index("ix_bwcp_sender_type", "bwcp_messages", ["sender_agent", "message_type"])
    op.create_index("ix_bwcp_delivered", "bwcp_messages", ["delivered"])

    # Create LeadScoreHistory table
    op.create_table(
        "lead_score_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_leads.id"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("previous_score", sa.Integer()),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("email_domain_score", sa.Integer(), server_default="0"),
        sa.Column("source_score", sa.Integer(), server_default="0"),
        sa.Column("behavior_score", sa.Integer(), server_default="0"),
        sa.Column("recency_score", sa.Integer(), server_default="0"),
        sa.Column("ai_rationale", sa.Text()),
        sa.Column("ai_model", sa.String(100)),
        sa.Column("triggered_by", sa.String(100), nullable=False),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_lead_score_history_lead_id", "lead_score_history", ["lead_id", "created_at"]
    )

    # Create PromptVersion table
    op.create_table(
        "prompt_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("prompt_key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text()),
        sa.Column("example_few_shot", postgresql.JSONB),
        sa.Column("model_config", postgresql.JSONB, server_default="{}"),
        sa.Column("expected_output_schema", postgresql.JSONB),
        sa.Column("is_active", sa.Boolean(), server_default="false"),
        sa.Column("deprecated_at", sa.DateTime(timezone=True)),
        sa.Column("total_calls", sa.Integer(), server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), server_default="0.0"),
        sa.Column("success_rate", sa.Float(), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("prompt_key", "version", name="ix_prompt_version"),
    )
    op.create_index("ix_prompt_active", "prompt_versions", ["prompt_key", "is_active"])

    # Create CampaignBudgetSnapshot table
    op.create_table(
        "campaign_budget_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_os_campaigns.id"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("budget_cents", sa.Integer(), nullable=False),
        sa.Column("spent_cents", sa.Integer(), server_default="0"),
        sa.Column("remaining_cents", sa.Integer(), nullable=False),
        sa.Column("spend_percentage", sa.Float(), server_default="0.0"),
        sa.Column("days_remaining", sa.Integer(), server_default="0"),
        sa.Column("projected_overrun", sa.Boolean(), server_default="false"),
        sa.Column("attributed_revenue_cents", sa.Integer(), server_default="0"),
        sa.Column("roas", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("campaign_id", "snapshot_date", name="ix_campaign_snapshot_date"),
    )

    # Create AttributionSummary table
    op.create_table(
        "attribution_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_campaigns.id")
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_os_leads.id")),
        sa.Column("touchpoints", sa.Integer(), server_default="0"),
        sa.Column("first_touch_date", sa.DateTime(timezone=True)),
        sa.Column("last_touch_date", sa.DateTime(timezone=True)),
        sa.Column("converted", sa.Boolean(), server_default="false"),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("conversion_value_cents", sa.Integer(), server_default="0"),
        sa.Column("attributed_revenue_cents", sa.Integer(), server_default="0"),
        sa.Column("channel_breakdown", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_attribution_period", "attribution_summaries", ["period_type", "period_start"]
    )
    op.create_index(
        "ix_attribution_campaign", "attribution_summaries", ["campaign_id", "period_start"]
    )

    # Add saga_state to orders table
    op.add_column(
        "revenue_os_orders", sa.Column("saga_state", sa.String(100), server_default="created")
    )
    op.create_index("ix_orders_saga_state", "revenue_os_orders", ["saga_state"])

    # Remove delivery_status from orders (it belongs to DeliveryEvent)
    op.drop_column("revenue_os_orders", "delivery_status")

    # Release advisory lock
    op.execute("SELECT pg_advisory_unlock(123456789)")


def downgrade() -> None:
    # Acquire advisory lock
    op.execute("SELECT pg_advisory_lock(123456789)")

    # Drop new tables (in reverse dependency order)
    op.drop_table("attribution_summaries")
    op.drop_table("campaign_budget_snapshots")
    op.drop_table("prompt_versions")
    op.drop_table("lead_score_history")
    op.drop_table("bwcp_messages")
    op.drop_table("outbox_events")

    # Restore delivery_status to orders
    op.add_column(
        "revenue_os_orders", sa.Column("delivery_status", sa.String(50), server_default="queued")
    )

    # Remove saga_state from orders
    op.drop_column("revenue_os_orders", "saga_state")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS agenttype")
    op.execute("DROP TYPE IF EXISTS bwcpmessagetype")

    # Release advisory lock
    op.execute("SELECT pg_advisory_unlock(123456789)")
