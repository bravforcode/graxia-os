"""Revenue OS Round 3 fixes - schema updates

Revision ID: 006
Revises: 4497f1eedc0b
Create Date: 2026-04-26

Changes:
1. Add 'archived' to campaign_status check constraint
2. Update approvals.item_type check constraint (remove 'email_draft', keep 'ai_draft')
3. Add partial index on webhook_events.processed_at (only index non-null values)
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "4497f1eedc0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply Round 3 schema fixes."""

    # 1. Update campaign_status constraint to include 'archived' (only if table exists)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'revenue_campaigns') THEN
                ALTER TABLE revenue_campaigns DROP CONSTRAINT IF EXISTS ck_campaigns_status;
                ALTER TABLE revenue_campaigns ADD CONSTRAINT ck_campaigns_status
                    CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived'));
            END IF;
        END $$;
    """)

    # 2. Update approvals.item_type constraint (clarify to use 'ai_draft' only)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'approvals') THEN
                ALTER TABLE approvals DROP CONSTRAINT IF EXISTS ck_approvals_item_type;
                ALTER TABLE approvals ADD CONSTRAINT ck_approvals_item_type
                    CHECK (item_type IN ('ai_draft', 'campaign', 'spend'));
            END IF;
        END $$;
    """)

    # 3. Add partial index on webhook_events.processed_at (only non-null values)
    # This improves query performance for processed webhooks
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'webhook_events') THEN
                CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_webhook_events_processed_at_partial
                ON webhook_events (processed_at)
                WHERE processed_at IS NOT NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert Round 3 schema fixes."""

    # 1. Revert campaign_status constraint (remove 'archived')
    op.execute("""
        ALTER TABLE revenue_campaigns
        DROP CONSTRAINT IF EXISTS ck_campaigns_status
    """)
    op.execute("""
        ALTER TABLE revenue_campaigns
        ADD CONSTRAINT ck_campaigns_status
        CHECK (status IN ('draft', 'active', 'paused', 'completed'))
    """)

    # 2. Revert approvals.item_type constraint (add back 'email_draft')
    op.execute("""
        ALTER TABLE approvals
        DROP CONSTRAINT IF EXISTS ck_approvals_item_type
    """)
    op.execute("""
        ALTER TABLE approvals
        ADD CONSTRAINT ck_approvals_item_type
        CHECK (item_type IN ('email_draft', 'campaign', 'spend', 'ai_draft'))
    """)

    # 3. Drop partial index
    op.execute("""
        DROP INDEX CONCURRENTLY IF EXISTS ix_webhook_events_processed_at_partial
    """)
