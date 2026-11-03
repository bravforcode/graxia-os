"""Converge content_drafts.organization_id for the tenant-scoped ContentDraft model.

Revision 002 already adds the column on databases that ran it, so this is a
no-op there. Databases created without it get the column, a backfill from the
draft's parent opportunity, submission or contact, and the NOT NULL, index and
foreign key the TenantMixin mapping expects.

Revision ID: 041_content_draft_tenancy
Revises: 040_audit_logs_table
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "041_content_draft_tenancy"
down_revision: str | Sequence[str] | None = "040_audit_logs_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "content_drafts"
_FK = "fk_content_drafts_organization_id_organizations"
_INDEX = "ix_content_drafts_organization_id"
_PARENTS = (
    ("opportunities", "opportunity_id"),
    ("submissions", "submission_id"),
    ("contacts", "contact_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return

    columns = {column["name"]: column for column in inspector.get_columns(_TABLE)}
    if "organization_id" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        columns = {column["name"]: column for column in sa.inspect(bind).get_columns(_TABLE)}

    if columns["organization_id"].get("nullable", True):
        # Parent table and column names come from the fixed list above.
        for parent, column in _PARENTS:
            if column not in columns or not sa.inspect(bind).has_table(parent):
                continue
            op.execute(
                sa.text(
                    f"UPDATE {_TABLE} SET organization_id = {parent}.organization_id "
                    f"FROM {parent} WHERE {_TABLE}.organization_id IS NULL "
                    f"AND {_TABLE}.{column} = {parent}.id"
                )
            )
        op.execute(
            sa.text(
                f"UPDATE {_TABLE} SET organization_id = "
                "'00000000-0000-0000-0000-000000000001' "
                "WHERE organization_id IS NULL"
            )
        )
        op.alter_column(_TABLE, "organization_id", nullable=False)

    inspector = sa.inspect(bind)
    if _INDEX not in {index.get("name") for index in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["organization_id"], unique=False)

    inspector = sa.inspect(bind)
    if not any(
        fk.get("constrained_columns") == ["organization_id"]
        and fk.get("referred_table") == "organizations"
        for fk in inspector.get_foreign_keys(_TABLE)
    ):
        op.create_foreign_key(
            _FK, _TABLE, "organizations", ["organization_id"], ["id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    # The column may predate this revision (002), so downgrade never drops it.
    pass
