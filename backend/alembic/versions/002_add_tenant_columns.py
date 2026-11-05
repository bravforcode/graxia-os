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

_TABLES = (
    ("contacts", "fk_contacts_organization_id_organizations"),
    ("opportunities", "fk_opportunities_organization_id_organizations"),
    ("content_drafts", "fk_content_drafts_organization_id_organizations"),
    ("approval_requests", "fk_approval_requests_organization_id_organizations"),
    ("automation_runs", "fk_automation_runs_organization_id_organizations"),
    ("job_postings", "fk_job_postings_organization_id_organizations"),
    ("submissions", "fk_submissions_organization_id_organizations"),
    ("email_threads", "fk_email_threads_organization_id_organizations"),
)


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _has_matching_foreign_key(inspector: sa.Inspector, table_name: str) -> bool:
    return any(
        foreign_key.get("constrained_columns") == ["organization_id"]
        and foreign_key.get("referred_table") == "organizations"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def _has_named_foreign_key(
    inspector: sa.Inspector, table_name: str, name: str
) -> bool:
    return any(
        foreign_key.get("name") == name
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def upgrade() -> None:
    """Converge legacy tenant columns without duplicating baseline DDL."""
    bind = op.get_bind()

    for table_name, fk_name in _TABLES:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        if not inspector.has_table("organizations"):
            raise RuntimeError("organizations must exist before tenant columns are migrated")

        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "organization_id" not in columns:
            op.add_column(
                table_name,
                sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
            )

        inspector = sa.inspect(bind)
        index_name = f"ix_{table_name}_organization_id"
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, ["organization_id"], unique=False)

        inspector = sa.inspect(bind)
        if not _has_matching_foreign_key(inspector, table_name):
            op.create_foreign_key(
                fk_name,
                table_name,
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="CASCADE",
            )

        # Table names come from the fixed allowlist above; values are not user input.
        op.execute(
            sa.text(
                f"UPDATE {table_name} SET organization_id = "
                "'00000000-0000-0000-0000-000000000001' "
                "WHERE organization_id IS NULL"
            )
        )
        op.alter_column(table_name, "organization_id", nullable=False)


def downgrade() -> None:
    """Remove only tenant objects explicitly owned by revision 002."""
    bind = op.get_bind()

    for table_name, fk_name in _TABLES:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "organization_id" not in columns or not _has_named_foreign_key(
            inspector, table_name, fk_name
        ):
            # Baseline-created tenant columns have no revision-002 FK name.
            continue

        op.alter_column(table_name, "organization_id", nullable=True)
        op.drop_constraint(fk_name, table_name=table_name, type_="foreignkey")

        inspector = sa.inspect(bind)
        index_name = f"ix_{table_name}_organization_id"
        if index_name in _index_names(inspector, table_name):
            op.drop_index(index_name, table_name=table_name)
        op.drop_column(table_name, "organization_id")
