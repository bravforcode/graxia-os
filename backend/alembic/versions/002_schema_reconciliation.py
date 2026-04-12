"""schema reconciliation

Revision ID: 002_schema_reconciliation
Revises: 001_enterprise_baseline
Create Date: 2026-04-12
"""

from collections.abc import Sequence

from alembic import op

from app.models import Base

# revision identifiers, used by Alembic.
revision: str = "002_schema_reconciliation"
down_revision: str | None = "001_enterprise_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        ALTER TABLE audit_log
            ADD COLUMN IF NOT EXISTS event_id UUID NOT NULL DEFAULT gen_random_uuid(),
            ADD COLUMN IF NOT EXISTS event_type VARCHAR(100) NOT NULL DEFAULT 'legacy.audit',
            ADD COLUMN IF NOT EXISTS event_category VARCHAR(50) NOT NULL DEFAULT 'system',
            ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'INFO',
            ADD COLUMN IF NOT EXISTS user_id UUID,
            ADD COLUMN IF NOT EXISTS session_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64),
            ADD COLUMN IF NOT EXISTS user_agent TEXT,
            ADD COLUMN IF NOT EXISTS request_path VARCHAR(500),
            ADD COLUMN IF NOT EXISTS request_method VARCHAR(16),
            ADD COLUMN IF NOT EXISTS outcome VARCHAR(20) NOT NULL DEFAULT 'success',
            ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS checksum VARCHAR(64) NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE contacts
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE opportunities
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE submissions
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contacts_company_deleted_created_at
            ON contacts (company, is_deleted, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contacts_email_deleted
            ON contacts (email, is_deleted)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_opportunities_status_deleted_found_at
            ON opportunities (status, is_deleted, found_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_opportunities_decision_deleted_score
            ON opportunities (decision, is_deleted, total_score)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_submissions_status_deleted_created_at
            ON submissions (status, is_deleted, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_submissions_opportunity_deleted_sent_at
            ON submissions (opportunity_id, is_deleted, sent_at)
        """
    )


def downgrade() -> None:
    # Reconciliation migrations are intentionally not destructive.
    pass
