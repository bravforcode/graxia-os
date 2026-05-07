"""add_performance_indexes

Revision ID: 89d09d4d6b03
Revises: 006
Create Date: 2026-04-26 16:44:41.746124

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "89d09d4d6b03"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Helper function to create index only if table and column exist
    def safe_create_index(index_name, table_name, columns, **kwargs):
        cols = ", ".join(columns)  # No quotes, just column names
        "UNIQUE " if kwargs.get("unique") else ""
        using = f"USING {kwargs.get('postgresql_using')} " if kwargs.get("postgresql_using") else ""
        ops = ""
        if kwargs.get("postgresql_ops"):
            # Build ops string like: (created_at DESC)
            op_items = [f"{col} {kwargs.get('postgresql_ops')}" for col in columns]
            ops = f"({', '.join(op_items)})"
        else:
            ops = f"({cols})"

        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}') THEN
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = '{table_name}' AND column_name = '{columns[0]}') THEN
                        EXECUTE 'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {using}{ops}';
                    END IF;
                END IF;
            END $$;
        """)

    # Opportunities indexes (only if table exists)
    safe_create_index("idx_opportunities_status", "opportunities", ["status"])
    safe_create_index(
        "idx_opportunities_score",
        "opportunities",
        ["total_score"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )
    safe_create_index("idx_opportunities_deadline", "opportunities", ["deadline"])
    safe_create_index(
        "idx_opportunities_found_at",
        "opportunities",
        ["found_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )
    safe_create_index(
        "idx_opportunities_created_at",
        "opportunities",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )

    # Submissions indexes
    safe_create_index("idx_submissions_status", "submissions", ["status"])
    safe_create_index("idx_submissions_opportunity", "submissions", ["opportunity_id"])
    safe_create_index(
        "idx_submissions_sent_at",
        "submissions",
        ["sent_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )
    safe_create_index(
        "idx_submissions_created_at",
        "submissions",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )

    # Contacts indexes
    safe_create_index("idx_contacts_email", "contacts", ["email"], unique=True)
    safe_create_index("idx_contacts_company", "contacts", ["company"])
    safe_create_index(
        "idx_contacts_last_contacted",
        "contacts",
        ["last_contacted_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )

    # Tasks indexes
    safe_create_index("idx_tasks_status", "tasks", ["status"])
    safe_create_index("idx_tasks_priority", "tasks", ["priority"])
    safe_create_index("idx_tasks_due_date", "tasks", ["due_date"])
    safe_create_index(
        "idx_tasks_created_at",
        "tasks",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )

    # Drafts indexes
    safe_create_index("idx_drafts_status", "drafts", ["status"])
    safe_create_index("idx_drafts_opportunity", "drafts", ["opportunity_id"])
    safe_create_index(
        "idx_drafts_created_at",
        "drafts",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )

    # Users indexes
    safe_create_index("idx_users_email", "users", ["email"], unique=True)
    safe_create_index(
        "idx_users_created_at",
        "users",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops="DESC",
    )


def downgrade() -> None:
    # Drop all indexes in reverse order
    op.drop_index("idx_users_created_at", "users")
    op.drop_index("idx_users_email", "users")

    op.drop_index("idx_drafts_created_at", "drafts")
    op.drop_index("idx_drafts_opportunity", "drafts")
    op.drop_index("idx_drafts_status", "drafts")

    op.drop_index("idx_tasks_created_at", "tasks")
    op.drop_index("idx_tasks_due_date", "tasks")
    op.drop_index("idx_tasks_priority", "tasks")
    op.drop_index("idx_tasks_status", "tasks")

    op.drop_index("idx_contacts_last_contacted", "contacts")
    op.drop_index("idx_contacts_company", "contacts")
    op.drop_index("idx_contacts_email", "contacts")

    op.drop_index("idx_submissions_created_at", "submissions")
    op.drop_index("idx_submissions_sent_at", "submissions")
    op.drop_index("idx_submissions_opportunity", "submissions")
    op.drop_index("idx_submissions_status", "submissions")

    op.drop_index("idx_opportunities_created_at", "opportunities")
    op.drop_index("idx_opportunities_found_at", "opportunities")
    op.drop_index("idx_opportunities_deadline", "opportunities")
    op.drop_index("idx_opportunities_score", "opportunities")
    op.drop_index("idx_opportunities_status", "opportunities")
