"""Add composite indexes for common query patterns [H-03]

Revision ID: 018_add_composite_query_indexes
Revises: 017_add_gin_fulltext_indexes
Create Date: 2026-05-07

This migration adds composite indexes to optimize common query patterns:
- opportunities: (user_id, status), (status, total_score), (user_id, created_at)
- contacts: (user_id, company), (user_id, is_deleted)
- email_threads: (status, last_message_at), (category, priority)
- assistant_tasks: (user_id, status), (status, priority), (user_id, due_date)

All indexes are created CONCURRENTLY to avoid table locks in production.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "018_add_composite_query_indexes"
down_revision: str | None = "017_add_gin_fulltext_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create composite indexes using CONCURRENT mode to avoid locking tables.
    
    Note: CREATE INDEX CONCURRENTLY cannot run inside a transaction block,
    so we use op.execute with proper connection handling.
    """
    
    # Get connection and set autocommit for CONCURRENT index creation
    conn = op.get_bind()
    
    # Opportunities indexes - optimize filtered list queries
    # Pattern: WHERE user_id = ? AND status = ?
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_status 
        ON opportunities (user_id, status) 
        WHERE is_deleted = false
        """
    )
    
    # Pattern: WHERE status = ? ORDER BY total_score DESC
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_status_score 
        ON opportunities (status, total_score DESC NULLS LAST) 
        WHERE is_deleted = false
        """
    )
    
    # Pattern: WHERE user_id = ? ORDER BY created_at DESC (for user's opportunity feed)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_created 
        ON opportunities (user_id, found_at DESC NULLS LAST) 
        WHERE is_deleted = false
        """
    )
    
    # Pattern: WHERE user_id = ? AND decision = ? (for decision-based filtering)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_opportunities_user_decision 
        ON opportunities (user_id, decision) 
        WHERE is_deleted = false
        """
    )
    
    # Contacts indexes - optimize organization and email lookups
    # Pattern: WHERE user_id = ? AND company = ?
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_company 
        ON contacts (user_id, company) 
        WHERE is_deleted = false
        """
    )
    
    # Pattern: WHERE user_id = ? AND is_deleted = false
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_active 
        ON contacts (user_id) 
        WHERE is_deleted = false
        """
    )
    
    # Pattern: WHERE email = ? AND is_deleted = false (unique email lookup)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_email_active 
        ON contacts (email) 
        WHERE is_deleted = false AND email IS NOT NULL
        """
    )
    
    # Pattern: WHERE user_id = ? AND contact_type = ?
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_contacts_user_type 
        ON contacts (user_id, contact_type) 
        WHERE is_deleted = false
        """
    )
    
    # Email threads indexes - optimize status and priority queries
    # Pattern: WHERE status = ? ORDER BY last_message_at DESC
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_status_last_msg 
        ON email_threads (status, last_message_at DESC NULLS LAST)
        """
    )
    
    # Pattern: WHERE category = ? ORDER BY priority DESC
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_category_priority 
        ON email_threads (category, priority DESC)
        """
    )
    
    # Pattern: WHERE status = 'unread' AND priority >= 8 (urgent unread emails)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_email_threads_urgent_unread 
        ON email_threads (status, priority DESC) 
        WHERE status = 'unread' AND priority >= 8
        """
    )
    
    # Assistant tasks indexes - optimize user task queries
    # Pattern: WHERE user_id = ? AND status = ?
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_status 
        ON assistant_tasks (user_id, status)
        """
    )
    
    # Pattern: WHERE status = ? ORDER BY priority DESC
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_status_priority 
        ON assistant_tasks (status, priority DESC)
        """
    )
    
    # Pattern: WHERE user_id = ? ORDER BY due_date ASC (user's upcoming tasks)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_due 
        ON assistant_tasks (user_id, due_date ASC NULLS LAST)
        """
    )
    
    # Pattern: WHERE status = 'pending' AND due_date < NOW() (overdue tasks)
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_overdue 
        ON assistant_tasks (status, due_date ASC) 
        WHERE status = 'pending' AND due_date IS NOT NULL
        """
    )
    
    # Pattern: WHERE user_id = ? AND status = 'pending' ORDER BY priority DESC
    conn.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assistant_tasks_user_pending_priority 
        ON assistant_tasks (user_id, priority DESC) 
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    """
    Drop all composite indexes created in upgrade.
    
    Note: DROP INDEX CONCURRENTLY also requires autocommit mode.
    """
    
    conn = op.get_bind()
    
    # Drop assistant_tasks indexes
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_assistant_tasks_user_pending_priority")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_assistant_tasks_overdue")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_assistant_tasks_user_due")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_assistant_tasks_status_priority")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_assistant_tasks_user_status")
    
    # Drop email_threads indexes
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_email_threads_urgent_unread")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_email_threads_category_priority")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_email_threads_status_last_msg")
    
    # Drop contacts indexes
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_contacts_user_type")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_contacts_email_active")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_contacts_user_active")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_contacts_user_company")
    
    # Drop opportunities indexes
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_opportunities_user_decision")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_opportunities_user_created")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_opportunities_status_score")
    conn.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_opportunities_user_status")
