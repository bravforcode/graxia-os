"""Add GIN full-text search indexes

Revision ID: 017_add_gin_fulltext_indexes
Revises: 016_add_check_constraints
Create Date: 2026-04-30

Performance: tsvector GIN indexes cut full-text query time from O(n) table scans
to O(log n) index lookups. Concurrent creation avoids locking.
"""

from alembic import op

revision: str = "017_add_gin_fulltext_indexes"
down_revision: str = "016_add_check_constraints"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return  # GIN is Postgres-only; SQLite test DB skips this migration

    # opportunities — title + description full-text (CONCURRENTLY to avoid lock)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_opportunities_fts
        ON opportunities
        USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')))
    """)

    # contacts — name + company full-text
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_contacts_fts
        ON contacts
        USING GIN (to_tsvector('english', coalesce(name, '') || ' ' || coalesce(company, '')))
    """)

    # knowledge_documents — title + content full-text
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_knowledge_documents_fts
        ON knowledge_documents
        USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, '')))
    """)

    # email_threads — subject full-text
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_email_threads_subject_fts
        ON email_threads
        USING GIN (to_tsvector('english', coalesce(subject, '')))
    """)

    # job_postings — title + description full-text
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_job_postings_fts
        ON job_postings
        USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')))
    """)


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_job_postings_fts")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_email_threads_subject_fts")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_knowledge_documents_fts")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_contacts_fts")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_opportunities_fts")
