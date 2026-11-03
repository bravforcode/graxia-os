"""Add optional composite indexes for common query patterns.

Revision ID: 018_add_composite_query_indexes
Revises: 017_add_gin_fulltext_indexes
Create Date: 2026-05-07

Indexes are created concurrently when the target table and columns exist.
The guards keep this performance-only revision compatible with deployments
whose baseline schema intentionally omits one of the older query fields.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_add_composite_query_indexes"
down_revision: str | None = "017_add_gin_fulltext_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    (
        "idx_opportunities_user_status",
        "opportunities",
        {"user_id", "status", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_status
        ON opportunities (user_id, status)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_opportunities_status_score",
        "opportunities",
        {"status", "total_score", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_status_score
        ON opportunities (status, total_score DESC NULLS LAST)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_opportunities_user_created",
        "opportunities",
        {"user_id", "found_at", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_created
        ON opportunities (user_id, found_at DESC NULLS LAST)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_opportunities_user_decision",
        "opportunities",
        {"user_id", "decision", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_decision
        ON opportunities (user_id, decision)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_contacts_user_company",
        "contacts",
        {"user_id", "company", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_company
        ON contacts (user_id, company)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_contacts_user_active",
        "contacts",
        {"user_id", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_active
        ON contacts (user_id)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_contacts_email_active",
        "contacts",
        {"email", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_email_active
        ON contacts (email)
        WHERE is_deleted = false AND email IS NOT NULL
        """,
    ),
    (
        "idx_contacts_user_type",
        "contacts",
        {"user_id", "contact_type", "is_deleted"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_type
        ON contacts (user_id, contact_type)
        WHERE is_deleted = false
        """,
    ),
    (
        "idx_email_threads_status_last_msg",
        "email_threads",
        {"status", "last_message_at"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_status_last_msg
        ON email_threads (status, last_message_at DESC NULLS LAST)
        """,
    ),
    (
        "idx_email_threads_category_priority",
        "email_threads",
        {"category", "priority"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_category_priority
        ON email_threads (category, priority DESC)
        """,
    ),
    (
        "idx_email_threads_urgent_unread",
        "email_threads",
        {"status", "priority"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_urgent_unread
        ON email_threads (status, priority DESC)
        WHERE status = 'unread' AND priority >= 8
        """,
    ),
    (
        "idx_assistant_tasks_user_status",
        "assistant_tasks",
        {"user_id", "status"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_status
        ON assistant_tasks (user_id, status)
        """,
    ),
    (
        "idx_assistant_tasks_status_priority",
        "assistant_tasks",
        {"status", "priority"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_status_priority
        ON assistant_tasks (status, priority DESC)
        """,
    ),
    (
        "idx_assistant_tasks_user_due",
        "assistant_tasks",
        {"user_id", "due_date"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_due
        ON assistant_tasks (user_id, due_date ASC NULLS LAST)
        """,
    ),
    (
        "idx_assistant_tasks_overdue",
        "assistant_tasks",
        {"status", "due_date"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_overdue
        ON assistant_tasks (status, due_date ASC)
        WHERE status = 'pending' AND due_date IS NOT NULL
        """,
    ),
    (
        "idx_assistant_tasks_user_pending_priority",
        "assistant_tasks",
        {"user_id", "priority", "status"},
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_pending_priority
        ON assistant_tasks (user_id, priority DESC)
        WHERE status = 'pending'
        """,
    ),
)


def _available_indexes(bind: sa.Connection) -> list[tuple[str, str]]:
    inspector = sa.inspect(bind)
    available: list[tuple[str, str]] = []
    for index_name, table_name, columns, statement in _INDEXES:
        if not inspector.has_table(table_name):
            continue
        table_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if columns.issubset(table_columns):
            available.append((index_name, statement))
    return available


def upgrade() -> None:
    """Create compatible performance indexes outside the DDL transaction."""
    bind = op.get_bind()
    statements = _available_indexes(bind)
    with op.get_context().autocommit_block():
        for _, statement in statements:
            bind.execute(sa.text(statement))


def downgrade() -> None:
    """Drop only indexes declared by this revision."""
    bind = op.get_bind()
    index_names = [index[0] for index in _INDEXES]
    with op.get_context().autocommit_block():
        for index_name in reversed(index_names):
            bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
