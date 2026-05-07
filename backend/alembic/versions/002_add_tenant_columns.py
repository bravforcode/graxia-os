"""Add organization_id to all tenant-scoped tables

Revision ID: 002
Revises: 001
Create Date: 2025-01-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add organization_id to all tenant-scoped tables
    tables = [
        ("contacts", "fk_contacts_organization_id_organizations"),
        ("opportunities", "fk_opportunities_organization_id_organizations"),
        ("content_drafts", "fk_content_drafts_organization_id_organizations"),
        ("approval_requests", "fk_approval_requests_organization_id_organizations"),
        ("automation_runs", "fk_automation_runs_organization_id_organizations"),
        ("job_postings", "fk_job_postings_organization_id_organizations"),
        ("submissions", "fk_submissions_organization_id_organizations"),
        ("email_threads", "fk_email_threads_organization_id_organizations"),
    ]

    for table_name, fk_name in tables:
        # Add column
        op.add_column(
            table_name, sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True)
        )

        # Create index
        op.create_index(
            f"ix_{table_name}_organization_id", table_name, ["organization_id"], unique=False
        )

        # Create foreign key
        op.create_foreign_key(
            fk_name, table_name, "organizations", ["organization_id"], ["id"], ondelete="CASCADE"
        )

        # Migrate existing data to default org
        op.execute(
            sa.text(f"""
                UPDATE {table_name} 
                SET organization_id = '00000000-0000-0000-0000-000000000001'
                WHERE organization_id IS NULL
            """)
        )

        # Make column NOT NULL after migration
        op.alter_column(table_name, "organization_id", nullable=False)


def downgrade() -> None:
    # Drop foreign keys and indexes
    tables = [
        ("contacts", "fk_contacts_organization_id_organizations"),
        ("opportunities", "fk_opportunities_organization_id_organizations"),
        ("content_drafts", "fk_content_drafts_organization_id_organizations"),
        ("approval_requests", "fk_approval_requests_organization_id_organizations"),
        ("automation_runs", "fk_automation_runs_organization_id_organizations"),
        ("job_postings", "fk_job_postings_organization_id_organizations"),
        ("submissions", "fk_submissions_organization_id_organizations"),
        ("email_threads", "fk_email_threads_organization_id_organizations"),
    ]

    for table_name, fk_name in tables:
        # Make column nullable first
        op.alter_column(table_name, "organization_id", nullable=True)

        # Drop foreign key
        op.drop_constraint(fk_name, table_name=table_name, type_="foreignkey")

        # Drop index
        op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)

        # Drop column
        op.drop_column(table_name, "organization_id")
