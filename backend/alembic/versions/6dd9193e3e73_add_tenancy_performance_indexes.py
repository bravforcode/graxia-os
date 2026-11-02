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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, id_col, ts_col in TENANT_TABLES:
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not {"organization_id", id_col, ts_col}.issubset(columns):
            continue
        index_names = {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        # Index 1: (organization_id, id) for primary lookups
        index_name = f"ix_{table_name}_org_id_id"
        if index_name not in index_names:
            op.create_index(index_name, table_name, ["organization_id", id_col], unique=False)
        # Index 2: (organization_id, timestamp) for list/sort queries
        inspector = sa.inspect(bind)
        index_names = {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        index_name = f"ix_{table_name}_org_id_{ts_col}"
        if index_name not in index_names:
            op.create_index(index_name, table_name, ["organization_id", ts_col], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name, id_col, ts_col in TENANT_TABLES:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        index_names = {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        index_name = f"ix_{table_name}_org_id_id"
        if index_name in index_names:
            op.drop_index(index_name, table_name=table_name)
        inspector = sa.inspect(bind)
        index_names = {
            index["name"]
            for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        index_name = f"ix_{table_name}_org_id_{ts_col}"
        if index_name in index_names:
            op.drop_index(index_name, table_name=table_name)
