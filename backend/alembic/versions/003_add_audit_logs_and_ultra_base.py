"""Add audit and security tables with baseline-compatible DDL.

Revision ID: 003
Revises: 002
Create Date: 2026-05-05 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_TABLES = (
    "users",
    "organizations",
    "contacts",
    "opportunities",
    "submissions",
    "job_postings",
    "email_threads",
    "usage_logs",
)
_AUDIT_LOG_COLUMNS = frozenset(
    {
        "id",
        "organization_id",
        "user_id",
        "action",
        "resource_type",
        "resource_id",
        "before_data",
        "after_data",
        "ip_address",
        "user_agent",
        "request_id",
        "is_sensitive",
        "severity",
        "metadata",
        "created_at",
        "created_by_id",
    }
)
_SECURITY_EVENT_COLUMNS = frozenset(
    {
        "id",
        "organization_id",
        "event_type",
        "severity",
        "user_id",
        "ip_address",
        "user_agent",
        "description",
        "raw_data",
        "is_resolved",
        "resolved_at",
        "resolved_by_id",
        "resolution_notes",
        "created_at",
        "created_by_id",
    }
)
_FAILED_LOGIN_COLUMNS = frozenset(
    {
        "id",
        "organization_id",
        "email",
        "ip_address",
        "attempted_at",
        "failure_reason",
        "country_code",
        "city",
        "device_fingerprint",
        "created_at",
    }
)


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _has_matching_foreign_key(
    inspector: sa.Inspector,
    table_name: str,
    columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    return any(
        foreign_key.get("constrained_columns") == columns
        and foreign_key.get("referred_table") == referred_table
        and foreign_key.get("referred_columns") == referred_columns
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def _has_named_foreign_key(
    inspector: sa.Inspector, table_name: str, name: str
) -> bool:
    return any(
        foreign_key.get("name") == name
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def _create_index_if_possible(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not set(columns).issubset(_column_names(inspector, table_name)):
        return
    if index_name not in _index_names(inspector, table_name):
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_exact_table(
    inspector: sa.Inspector, table_name: str, expected_columns: frozenset[str]
) -> None:
    if inspector.has_table(table_name) and _column_names(inspector, table_name) == expected_columns:
        op.drop_table(table_name)


def _add_updated_by_column(bind: sa.Connection, table_name: str) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return

    if "updated_by_id" not in _column_names(inspector, table_name):
        op.add_column(
            table_name,
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    inspector = sa.inspect(bind)
    constraint_name = f"fk_{table_name}_updated_by_id_users"
    if not _has_matching_foreign_key(
        inspector, table_name, ["updated_by_id"], "users", ["id"]
    ):
        op.create_foreign_key(
            constraint_name,
            table_name,
            "users",
            ["updated_by_id"],
            ["id"],
            ondelete="SET NULL",
        )


def upgrade() -> None:
    """Create missing audit/security objects without duplicating baseline DDL."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "organizations.id",
                    name="fk_audit_log_organization_id_organizations",
                    ondelete="CASCADE",
                ),
                nullable=True,
            ),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "users.id",
                    name="fk_audit_log_user_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=False),
            sa.Column("resource_id", sa.String(100), nullable=True),
            sa.Column("before_data", postgresql.JSONB, nullable=True),
            sa.Column("after_data", postgresql.JSONB, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("request_id", sa.String(36), nullable=True),
            sa.Column("is_sensitive", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
            sa.Column("metadata", postgresql.JSONB, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "users.id",
                    name="fk_audit_log_created_by_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )

    inspector = sa.inspect(bind)
    _create_index_if_possible(
        inspector, "audit_log", "idx_audit_org_action_time", ["organization_id", "action", "created_at"]
    )
    _create_index_if_possible(
        inspector, "audit_log", "idx_audit_user_time", ["user_id", "created_at"]
    )
    _create_index_if_possible(
        inspector, "audit_log", "idx_audit_resource", ["resource_type", "resource_id"]
    )
    _create_index_if_possible(
        inspector, "audit_log", "idx_audit_sensitive", ["is_sensitive", "created_at"]
    )

    inspector = sa.inspect(bind)
    if not inspector.has_table("security_event"):
        op.create_table(
            "security_event",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "organizations.id",
                    name="fk_security_event_organization_id_organizations",
                    ondelete="CASCADE",
                ),
                nullable=True,
            ),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False, server_default="low"),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "users.id",
                    name="fk_security_event_user_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("ip_address", sa.String(45), nullable=False),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("raw_data", postgresql.JSONB, nullable=True),
            sa.Column("is_resolved", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "resolved_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "users.id",
                    name="fk_security_event_resolved_by_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("resolution_notes", sa.String(500), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "users.id",
                    name="fk_security_event_created_by_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )

    inspector = sa.inspect(bind)
    _create_index_if_possible(
        inspector, "security_event", "idx_security_event_type_severity", ["event_type", "severity"]
    )
    _create_index_if_possible(
        inspector, "security_event", "idx_security_ip_time", ["ip_address", "created_at"]
    )
    _create_index_if_possible(
        inspector, "security_event", "idx_security_unresolved", ["is_resolved", "severity"]
    )

    inspector = sa.inspect(bind)
    if not inspector.has_table("failed_login_attempt"):
        op.create_table(
            "failed_login_attempt",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("ip_address", sa.String(45), nullable=False),
            sa.Column(
                "attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column("failure_reason", sa.String(100), nullable=False),
            sa.Column("country_code", sa.String(2), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("device_fingerprint", sa.String(64), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
        )

    inspector = sa.inspect(bind)
    _create_index_if_possible(
        inspector, "failed_login_attempt", "idx_failed_login_email_time", ["email", "attempted_at"]
    )
    _create_index_if_possible(
        inspector, "failed_login_attempt", "idx_failed_login_ip_time", ["ip_address", "attempted_at"]
    )

    for table_name in _AUDIT_TABLES:
        _add_updated_by_column(bind, table_name)


def downgrade() -> None:
    """Drop only exact-shape objects created by this revision."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_exact_table(inspector, "failed_login_attempt", _FAILED_LOGIN_COLUMNS)
    inspector = sa.inspect(bind)
    _drop_exact_table(inspector, "security_event", _SECURITY_EVENT_COLUMNS)
    inspector = sa.inspect(bind)
    _drop_exact_table(inspector, "audit_log", _AUDIT_LOG_COLUMNS)

    for table_name in _AUDIT_TABLES:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        if "updated_by_id" not in _column_names(inspector, table_name):
            continue
        constraint_name = f"fk_{table_name}_updated_by_id_users"
        if not _has_named_foreign_key(inspector, table_name, constraint_name):
            continue
        op.drop_constraint(constraint_name, table_name=table_name, type_="foreignkey")
        op.drop_column(table_name, "updated_by_id")
