"""Add organizations and usage_logs tables

Revision ID: 001
Revises:
Create Date: 2025-01-05 00:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
_ORGANIZATION_COLUMNS = frozenset(
    {
        "id",
        "name",
        "slug",
        "stripe_customer_id",
        "stripe_subscription_id",
        "plan",
        "status",
        "trial_ends_at",
        "monthly_lead_limit",
        "monthly_ai_credit_cents",
        "seats",
        "settings",
        "created_at",
        "updated_at",
    }
)
_USAGE_LOG_COLUMNS = frozenset(
    {
        "id",
        "organization_id",
        "user_id",
        "feature",
        "quantity",
        "cost_usd",
        "meta",
        "created_at",
    }
)


def _table_columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _foreign_key_matches(
    foreign_key: dict,
    *,
    name: str,
    columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    return foreign_key.get("name") == name or (
        foreign_key.get("constrained_columns") == columns
        and foreign_key.get("referred_table") == referred_table
        and foreign_key.get("referred_columns") == referred_columns
    )


def _foreign_key_name(
    inspector: sa.Inspector,
    table_name: str,
    *,
    name: str,
    columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> str | None:
    for foreign_key in inspector.get_foreign_keys(table_name):
        if _foreign_key_matches(
            foreign_key,
            name=name,
            columns=columns,
            referred_table=referred_table,
            referred_columns=referred_columns,
        ):
            return foreign_key.get("name")
    return None

def _has_foreign_key(
    inspector: sa.Inspector,
    table_name: str,
    *,
    name: str,
    columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    return any(
        _foreign_key_matches(
            foreign_key,
            name=name,
            columns=columns,
            referred_table=referred_table,
            referred_columns=referred_columns,
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def _has_exact_columns(
    inspector: sa.Inspector, table_name: str, expected: frozenset[str]
) -> bool:
    return inspector.has_table(table_name) and _table_columns(inspector, table_name) == expected


def _ensure_index(
    inspector: sa.Inspector,
    *,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if index_name not in _index_names(inspector, table_name):
        op.create_index(op.f(index_name), table_name, columns, unique=False)


def _ensure_default_organization(
    bind: sa.Connection, inspector: sa.Inspector
) -> None:
    if not inspector.has_table("organizations"):
        return

    organization_columns = _table_columns(inspector, "organizations")
    required_columns = {
        "id",
        "name",
        "slug",
        "plan",
        "status",
        "monthly_lead_limit",
        "monthly_ai_credit_cents",
        "seats",
    }
    if not required_columns.issubset(organization_columns):
        return

    metadata = sa.MetaData()
    organizations = sa.Table("organizations", metadata, autoload_with=bind)
    now = datetime.now(UTC)
    default_org_value = (
        _DEFAULT_ORG_ID if bind.dialect.name == "postgresql" else str(_DEFAULT_ORG_ID)
    )
    defaults = {
        "id": default_org_value,
        "name": "Legacy Organization",
        "slug": "legacy",
        "plan": "free",
        "status": "active",
        "monthly_lead_limit": 10,
        "monthly_ai_credit_cents": 200,
        "seats": 1,
        "privacy_mode": False,
        "settings": {},
        "created_at": now,
        "updated_at": now,
    }
    values = {
        name: value for name, value in defaults.items() if name in organization_columns
    }

    for column in organizations.columns:
        if (
            not column.nullable
            and column.default is None
            and column.server_default is None
            and column.name not in values
        ):
            return

    if bind.dialect.name == "postgresql":
        statement = postgresql.insert(organizations).values(values).on_conflict_do_nothing()
    else:
        statement = sa.insert(organizations).values(values)
        if bind.dialect.name == "sqlite":
            statement = statement.prefix_with("OR IGNORE")
    bind.execute(statement)

    if not inspector.has_table("users"):
        return

    users = sa.Table("users", metadata, autoload_with=bind)
    if "organization_id" not in users.c:
        return

    organization_exists = sa.select(organizations.c.id).where(
        organizations.c.id == default_org_value
    )
    bind.execute(
        sa.update(users)
        .where(users.c.organization_id.is_(None))
        .where(sa.exists(organization_exists))
        .values(organization_id=default_org_value)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False),
            sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
            sa.Column("plan", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("monthly_lead_limit", sa.Integer(), nullable=False),
            sa.Column("monthly_ai_credit_cents", sa.Integer(), nullable=False),
            sa.Column("seats", sa.Integer(), nullable=False),
            sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
            sa.CheckConstraint("plan IN ('free','starter','pro')", name="ck_org_plan"),
            sa.CheckConstraint(
                "status IN ('active','trialing','past_due','canceled','suspended')",
                name="ck_org_status",
            ),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("organizations"):
        _ensure_index(
            inspector,
            table_name="organizations",
            index_name="ix_organizations_stripe_customer_id",
            columns=["stripe_customer_id"],
        )
        _ensure_index(
            inspector,
            table_name="organizations",
            index_name="ix_organizations_stripe_subscription_id",
            columns=["stripe_subscription_id"],
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("usage_logs"):
        op.create_table(
            "usage_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("feature", sa.String(length=50), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["organization_id"], ["organizations.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("usage_logs"):
        _ensure_index(
            inspector,
            table_name="usage_logs",
            index_name="ix_usage_logs_organization_id",
            columns=["organization_id"],
        )
        _ensure_index(
            inspector,
            table_name="usage_logs",
            index_name="ix_usage_logs_feature",
            columns=["feature"],
        )
        _ensure_index(
            inspector,
            table_name="usage_logs",
            index_name="ix_usage_logs_created_at",
            columns=["created_at"],
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("users"):
        user_columns = _table_columns(inspector, "users")
        if "organization_id" not in user_columns:
            op.add_column(
                "users",
                sa.Column(
                    "organization_id", postgresql.UUID(as_uuid=True), nullable=True
                ),
            )

        inspector = sa.inspect(bind)
        _ensure_index(
            inspector,
            table_name="users",
            index_name="ix_users_organization_id",
            columns=["organization_id"],
        )

        inspector = sa.inspect(bind)
        if not _has_foreign_key(
            inspector,
            "users",
            name="fk_users_organization_id_organizations",
            columns=["organization_id"],
            referred_table="organizations",
            referred_columns=["id"],
        ):
            op.create_foreign_key(
                "fk_users_organization_id_organizations",
                "users",
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="SET NULL",
            )

    _ensure_default_organization(bind, sa.inspect(bind))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Only exact legacy shapes are owned by this revision. Baseline-created
    # tables have additional columns and must remain untouched on downgrade.
    if not (
        _has_exact_columns(inspector, "organizations", _ORGANIZATION_COLUMNS)
        and _has_exact_columns(inspector, "usage_logs", _USAGE_LOG_COLUMNS)
    ):
        return

    usage_fk_name = _foreign_key_name(
        inspector,
        "usage_logs",
        name="fk_usage_logs_organization_id_organizations",
        columns=["organization_id"],
        referred_table="organizations",
        referred_columns=["id"],
    )
    if usage_fk_name:
        op.drop_constraint(
            usage_fk_name, table_name="usage_logs", type_="foreignkey"
        )

    inspector = sa.inspect(bind)
    users_fk_name = None
    if inspector.has_table("users") and "organization_id" in _table_columns(
        inspector, "users"
    ):
        users_fk_name = _foreign_key_name(
            inspector,
            "users",
            name="fk_users_organization_id_organizations",
            columns=["organization_id"],
            referred_table="organizations",
            referred_columns=["id"],
        )
    if users_fk_name:
        op.drop_constraint(users_fk_name, table_name="users", type_="foreignkey")

    for table_name, index_name in (
        ("usage_logs", "ix_usage_logs_created_at"),
        ("usage_logs", "ix_usage_logs_feature"),
        ("usage_logs", "ix_usage_logs_organization_id"),
        ("organizations", "ix_organizations_stripe_subscription_id"),
        ("organizations", "ix_organizations_stripe_customer_id"),
    ):
        inspector = sa.inspect(bind)
        if inspector.has_table(table_name) and index_name in _index_names(
            inspector, table_name
        ):
            op.drop_index(op.f(index_name), table_name=table_name)

    inspector = sa.inspect(bind)
    if (
        inspector.has_table("users")
        and "organization_id" in _table_columns(inspector, "users")
        and "ix_users_organization_id" in _index_names(inspector, "users")
    ):
        op.drop_index(op.f("ix_users_organization_id"), table_name="users")

    inspector = sa.inspect(bind)
    if inspector.has_table("users") and "organization_id" in _table_columns(
        inspector, "users"
    ):
        op.drop_column("users", "organization_id")

    inspector = sa.inspect(bind)
    if _has_exact_columns(inspector, "usage_logs", _USAGE_LOG_COLUMNS):
        op.drop_table("usage_logs")

    inspector = sa.inspect(bind)
    if _has_exact_columns(inspector, "organizations", _ORGANIZATION_COLUMNS):
        op.drop_table("organizations")
