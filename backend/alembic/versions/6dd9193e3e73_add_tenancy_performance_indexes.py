"""add_tenancy_performance_indexes

Revision ID: 6dd9193e3e73
Revises: cef7acf8e4ed
Create Date: 2026-05-12 18:51:57.703638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dd9193e3e73'
down_revision: Union[str, None] = 'cef7acf8e4ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# List of tables with their primary ID and primary timestamp column
TENANT_TABLES = [
    ("users", "id", "created_at"),
    ("usage_logs", "id", "created_at"),
    ("contacts", "id", "created_at"),
    ("opportunities", "id", "found_at"),
    ("content_drafts", "id", "created_at"),
    ("approval_requests", "id", "created_at"),
    ("automation_runs", "id", "created_at"),
    ("job_postings", "id", "created_at"),
    ("submissions", "id", "created_at"),
    ("email_threads", "id", "created_at"),
    ("agents", "id", "created_at"),
    ("agent_teams", "id", "created_at"),
    ("audit_logs", "id", "created_at"),
    ("openclaw_usage", "id", "created_at"),
    ("workflows", "id", "created_at"),
]

def upgrade() -> None:
    for table_name, id_col, ts_col in TENANT_TABLES:
        # Index 1: (organization_id, id) for primary lookups
        op.create_index(
            f"ix_{table_name}_org_id_id",
            table_name,
            ["organization_id", id_col],
            unique=False
        )
        # Index 2: (organization_id, timestamp) for list/sort queries
        op.create_index(
            f"ix_{table_name}_org_id_{ts_col}",
            table_name,
            ["organization_id", ts_col],
            unique=False
        )


def downgrade() -> None:
    for table_name, id_col, ts_col in TENANT_TABLES:
        op.drop_index(f"ix_{table_name}_org_id_id", table_name=table_name)
        op.drop_index(f"ix_{table_name}_org_id_{ts_col}", table_name=table_name)
