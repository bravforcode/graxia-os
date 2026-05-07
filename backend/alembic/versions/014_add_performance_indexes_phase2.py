"""Add performance indexes phase 2

Revision ID: 014_add_performance_indexes_phase2
Revises: 89d09d4d6b03
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "014_add_performance_indexes_phase2"
down_revision: str | None = "89d09d4d6b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Opportunities — is_deleted is hit on every query
    op.create_index(
        "ix_opportunities_is_deleted",
        "opportunities",
        ["is_deleted"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    # Audit logs — time-range compliance queries
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )
    # Submissions — pipeline status queries
    op.create_index(
        "ix_submissions_status_created_at",
        "submissions",
        ["status", "created_at"],
        postgresql_using="btree",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_status_created_at", table_name="submissions", if_exists=True)
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs", if_exists=True)
    op.drop_index("ix_opportunities_is_deleted", table_name="opportunities", if_exists=True)
