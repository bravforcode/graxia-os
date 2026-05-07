"""Add Missing updated_at Columns

Revision ID: 011_add_missing_updated_at_columns
Revises: 010_revenue_os_improvements
Create Date: 2026-04-26 12:01:00.000000

Description:
    Add missing updated_at columns to tables that don't have them yet
"""

import sqlalchemy as sa
from alembic import op

revision = "011_add_missing_updated_at_columns"
down_revision = "010_revenue_os_improvements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing updated_at columns"""

    # Lead Magnets
    op.add_column(
        "revenue_os_lead_magnets",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Content Ideas
    op.add_column(
        "revenue_os_content_ideas",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Content Posts
    op.add_column(
        "revenue_os_content_posts",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Approvals
    op.add_column(
        "revenue_os_approvals",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # AI Drafts
    op.add_column(
        "revenue_os_ai_drafts",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Email Outbox
    op.add_column(
        "revenue_os_email_outbox",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Automation Runs
    op.add_column(
        "revenue_os_automation_runs",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Incident Events
    op.add_column(
        "revenue_os_incident_events",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Webhook Events
    op.add_column(
        "revenue_os_webhook_events",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Tasks
    op.add_column(
        "revenue_os_tasks",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    print("✓ Added updated_at columns to 10 tables")


def downgrade() -> None:
    """Remove updated_at columns"""

    op.drop_column("revenue_os_tasks", "updated_at")
    op.drop_column("revenue_os_webhook_events", "updated_at")
    op.drop_column("revenue_os_incident_events", "updated_at")
    op.drop_column("revenue_os_automation_runs", "updated_at")
    op.drop_column("revenue_os_email_outbox", "updated_at")
    op.drop_column("revenue_os_ai_drafts", "updated_at")
    op.drop_column("revenue_os_approvals", "updated_at")
    op.drop_column("revenue_os_content_posts", "updated_at")
    op.drop_column("revenue_os_content_ideas", "updated_at")
    op.drop_column("revenue_os_lead_magnets", "updated_at")

    print("✓ Removed updated_at columns")
