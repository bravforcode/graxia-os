"""Reconcile tables and columns required by the current production ORM."""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "034_production_schema_reconcile"
down_revision: str | Sequence[str] | None = "033_safe_lead_magnet_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
_NEW_TABLES = (
    "privacy_consents",
    "breach_notifications",
    "compliance_audit_logs",
    "funnel_coupons",
    "funnel_reviews",
    "funnel_email_sequences",
    "funnel_bundles",
)
_TENANT_COLUMNS = (
    ("approval_requests", "fk_approval_requests_organization_id_organizations"),
    ("automation_runs", "fk_automation_runs_organization_id_organizations"),
)
_OTHER_COLUMNS = (
    ("audit_log", "metadata", postgresql.JSONB()),
    ("contacts", "status", sa.String(length=50)),
    ("funnel_checkout_sessions", "abandoned_email_sent_at", sa.DateTime(timezone=True)),
)
_CREATED_INDEXES = (
    ("ix_privacy_consents_organization_id", "privacy_consents", ("organization_id",), False),
    ("ix_privacy_consents_user_id", "privacy_consents", ("user_id",), False),
    ("ix_breach_notifications_organization_id", "breach_notifications", ("organization_id",), False),
    ("ix_audit_logs_actor_time", "compliance_audit_logs", ("actor_id", "created_at"), False),
    ("ix_audit_logs_event_time", "compliance_audit_logs", ("event_type", "created_at"), False),
    ("ix_audit_logs_gdpr", "compliance_audit_logs", ("gdpr_category", "created_at"), False),
    ("ix_audit_logs_target_time", "compliance_audit_logs", ("target_type", "target_id", "created_at"), False),
    ("ix_compliance_audit_logs_actor_id", "compliance_audit_logs", ("actor_id",), False),
    ("ix_compliance_audit_logs_created_at", "compliance_audit_logs", ("created_at",), False),
    ("ix_compliance_audit_logs_event_category", "compliance_audit_logs", ("event_category",), False),
    ("ix_compliance_audit_logs_event_type", "compliance_audit_logs", ("event_type",), False),
    ("ix_compliance_audit_logs_target_id", "compliance_audit_logs", ("target_id",), False),
    ("ix_funnel_coupons_code", "funnel_coupons", ("code",), True),
    ("ix_funnel_coupons_organization_id", "funnel_coupons", ("organization_id",), False),
    ("ix_funnel_reviews_organization_id", "funnel_reviews", ("organization_id",), False),
    ("ix_funnel_reviews_product_id", "funnel_reviews", ("product_id",), False),
    ("ix_funnel_email_sequences_organization_id", "funnel_email_sequences", ("organization_id",), False),
    ("ix_funnel_bundles_organization_id", "funnel_bundles", ("organization_id",), False),
)


def _inspect(bind: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _validate_preconditions(bind: sa.engine.Connection) -> None:
    inspector = _inspect(bind)
    required_tables = {
        "organizations",
        "users",
        "digital_products",
        "funnel_orders",
        "contacts",
        "approval_requests",
        "automation_runs",
        "audit_log",
        "funnel_checkout_sessions",
    }
    missing = sorted(required_tables.difference(inspector.get_table_names()))
    if missing:
        raise RuntimeError(f"034 prerequisites are missing: {', '.join(missing)}")

    existing_new_tables = sorted(name for name in _NEW_TABLES if inspector.has_table(name))
    if existing_new_tables:
        raise RuntimeError(
            "034 refuses pre-existing reconciliation tables: "
            + ", ".join(existing_new_tables)
        )

    expected_missing = {
        (table, "organization_id") for table, _ in _TENANT_COLUMNS
    } | {(table, column) for table, column, _ in _OTHER_COLUMNS}
    existing_columns = []
    for table, column in expected_missing:
        names = {item["name"] for item in inspector.get_columns(table)}
        if column in names:
            existing_columns.append(f"{table}.{column}")
    if existing_columns:
        raise RuntimeError(
            "034 refuses pre-existing reconciliation columns: "
            + ", ".join(sorted(existing_columns))
        )


def _backfill_organization_id(
    bind: sa.engine.Connection, table_name: str
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)
    organizations = sa.Table("organizations", metadata, autoload_with=bind)
    missing_count = bind.execute(
        sa.select(sa.func.count())
        .select_from(table)
        .where(table.c.organization_id.is_(None))
    ).scalar_one()
    if not missing_count:
        return

    organization_ids = list(bind.execute(sa.select(organizations.c.id)).scalars())
    if bind.dialect.name == "postgresql":
        organization_ids = [UUID(str(value)) for value in organization_ids]
    if _DEFAULT_ORGANIZATION_ID in organization_ids:
        organization_id = _DEFAULT_ORGANIZATION_ID
    elif len(organization_ids) == 1:
        organization_id = organization_ids[0]
    else:
        raise RuntimeError(
            f"Cannot safely backfill {table_name}.organization_id: "
            "no unique existing organization is available"
        )

    bind.execute(
        sa.update(table)
        .where(table.c.organization_id.is_(None))
        .values(organization_id=organization_id)
    )


def _add_tenant_column(
    bind: sa.engine.Connection, table_name: str, foreign_key_name: str
) -> None:
    column = sa.Column(
        "organization_id", sa.Uuid(as_uuid=True), nullable=True
    )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(column)
            batch.create_foreign_key(
                foreign_key_name,
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="CASCADE",
            )
    else:
        op.add_column(table_name, column)
        op.create_foreign_key(
            foreign_key_name,
            table_name,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )

    _backfill_organization_id(bind, table_name)
    inspector = _inspect(bind)
    organization_column = next(
        item
        for item in inspector.get_columns(table_name)
        if item["name"] == "organization_id"
    )
    if organization_column.get("nullable", True):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch:
                batch.alter_column(
                    "organization_id",
                    existing_type=sa.Uuid(as_uuid=True),
                    nullable=False,
                )
        else:
            op.alter_column(
                table_name,
                "organization_id",
                existing_type=sa.Uuid(as_uuid=True),
                nullable=False,
            )

    index_name = f"ix_{table_name}_organization_id"
    if index_name not in {item["name"] for item in _inspect(bind).get_indexes(table_name)}:
        op.create_index(index_name, table_name, ["organization_id"], unique=False)


def _create_new_tables() -> None:
    op.create_table(
        "privacy_consents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "purpose", name="uq_privacy_consent_user_purpose"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "breach_notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_subjects", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notified_regulator_at", sa.DateTime(timezone=True)),
        sa.Column("notification_deadline", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "compliance_audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_category", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True)),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_email", sa.String(length=255)),
        sa.Column("session_id", sa.String(length=255)),
        sa.Column("ip_address", sa.String(length=45)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("target_type", sa.String(length=50)),
        sa.Column("target_id", sa.Uuid(as_uuid=True)),
        sa.Column("action_description", sa.Text(), nullable=False),
        sa.Column("action_payload", sa.JSON()),
        sa.Column("action_result", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("contains_pii", sa.Integer()),
        sa.Column("data_retention_days", sa.Integer()),
        sa.Column("gdpr_category", sa.String(length=50)),
        sa.Column("legal_basis", sa.String(length=50)),
        sa.Column("previous_hash", sa.String(length=64)),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "funnel_coupons",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("coupon_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_uses", sa.Integer()),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True)),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("description", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.CheckConstraint("coupon_type IN ('percentage', 'fixed')", name="ck_coupon_type"),
        sa.CheckConstraint("status IN ('active', 'expired', 'disabled')", name="ck_coupon_status"),
        sa.CheckConstraint("discount_value > 0", name="ck_coupon_discount_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "funnel_reviews",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True)),
        sa.Column("contact_id", sa.Uuid(as_uuid=True)),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("body", sa.Text()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("is_verified_purchase", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        sa.CheckConstraint("status IN ('pending', 'published', 'hidden')", name="ck_review_status"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["funnel_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "funnel_email_sequences",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("delay_hours", sa.Integer(), nullable=False),
        sa.Column("subject_template", sa.String(length=500), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True)),
        sa.Column("total_sent", sa.Integer(), nullable=False),
        sa.Column("total_opened", sa.Integer(), nullable=False),
        sa.Column("total_clicked", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.CheckConstraint("trigger_type IN ('welcome', 'abandoned_cart', 'post_purchase', 'review_request', 'cross_sell', 'win_back')", name="ck_email_trigger_type"),
        sa.CheckConstraint("status IN ('active', 'paused', 'draft')", name="ck_email_seq_status"),
        sa.ForeignKeyConstraint(["product_id"], ["digital_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "funnel_bundles",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("cover_image_url", sa.Text()),
        sa.Column("product_ids", postgresql.JSONB()),
        sa.Column("sales_count", sa.Integer(), nullable=False),
        sa.Column("badge", sa.String(length=50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.CheckConstraint("discount_type IN ('percentage', 'fixed')", name="ck_bundle_discount_type"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_bundle_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_indexes(bind: sa.engine.Connection) -> None:
    for name, table_name, columns, unique in _CREATED_INDEXES:
        existing = {item["name"] for item in _inspect(bind).get_indexes(table_name)}
        if name not in existing:
            op.create_index(name, table_name, list(columns), unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    _validate_preconditions(bind)
    _create_new_tables()

    for table_name, foreign_key_name in _TENANT_COLUMNS:
        _add_tenant_column(bind, table_name, foreign_key_name)
    for table_name, column_name, column_type in _OTHER_COLUMNS:
        op.add_column(
            table_name,
            sa.Column(column_name, column_type, nullable=True),
        )
    _create_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = _inspect(bind)
    for table_name in _NEW_TABLES:
        if inspector.has_table(table_name):
            count = bind.execute(sa.text(f"SELECT count(*) FROM {table_name}")).scalar_one()
            if count:
                raise RuntimeError(
                    f"Cannot downgrade 034 while {table_name} contains data"
                )
    added_columns = [(table, "organization_id") for table, _ in _TENANT_COLUMNS]
    added_columns.extend((table, column) for table, column, _ in _OTHER_COLUMNS)
    for table_name, column_name in added_columns:
        if not inspector.has_table(table_name):
            continue
        columns = {item["name"] for item in inspector.get_columns(table_name)}
        if column_name in columns:
            count = bind.execute(
                sa.text(
                    f"SELECT count(*) FROM {table_name} "
                    f"WHERE {column_name} IS NOT NULL"
                )
            ).scalar_one()
            if count:
                raise RuntimeError(
                    f"Cannot downgrade 034 while {table_name}.{column_name} "
                    "contains data"
                )

    for table_name, foreign_key_name in reversed(_TENANT_COLUMNS):
        indexes = {item["name"] for item in inspector.get_indexes(table_name)}
        if f"ix_{table_name}_organization_id" in indexes:
            op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch:
                batch.drop_constraint(foreign_key_name, type_="foreignkey")
                batch.drop_column("organization_id")
        else:
            op.drop_constraint(foreign_key_name, table_name, type_="foreignkey")
            op.drop_column(table_name, "organization_id")

    for table_name, column_name, _column_type in reversed(_OTHER_COLUMNS):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch:
                batch.drop_column(column_name)
        else:
            op.drop_column(table_name, column_name)

    for table_name in reversed(_NEW_TABLES):
        op.drop_table(table_name)
