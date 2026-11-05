"""add consent state and idempotency for organic attribution."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "024_organic_attribution_consent"
down_revision: str | Sequence[str] | None = (
    "021_add_funnel_v5_models",
    "023_publish_claim_expiry",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("conversion_events"):
        columns = {column["name"] for column in inspector.get_columns("conversion_events")}
        if "idempotency_key" not in columns:
            op.add_column(
                "conversion_events",
                sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            )
        inspector = sa.inspect(bind)
        index_names = {
            index["name"]
            for index in inspector.get_indexes("conversion_events")
            if index.get("name")
        }
        if (
            "uq_conversion_events_org_idempotency" not in index_names
            and {"organization_id", "idempotency_key"}.issubset(
                {column["name"] for column in inspector.get_columns("conversion_events")}
            )
        ):
            op.create_index(
                "uq_conversion_events_org_idempotency",
                "conversion_events",
                ["organization_id", "idempotency_key"],
                unique=True,
            )

    if not inspector.has_table("contacts"):
        return
    columns = {column["name"] for column in inspector.get_columns("contacts")}
    additions = (
        (
            "marketing_consent",
            sa.Column(
                "marketing_consent",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        (
            "marketing_consent_at",
            sa.Column("marketing_consent_at", sa.DateTime(timezone=True), nullable=True),
        ),
        ("consent_version", sa.Column("consent_version", sa.String(length=100), nullable=True)),
        (
            "marketing_unsubscribed",
            sa.Column(
                "marketing_unsubscribed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        (
            "marketing_unsubscribed_at",
            sa.Column("marketing_unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        ),
    )
    for column_name, column in additions:
        if column_name not in columns:
            op.add_column("contacts", column)
            columns.add(column_name)

    inspector = sa.inspect(bind)
    check_names = {
        check["name"]
        for check in inspector.get_check_constraints("contacts")
        if check.get("name")
    }
    if "ck_contact_marketing_consent_audit" not in check_names:
        op.create_check_constraint(
            "ck_contact_marketing_consent_audit",
            "contacts",
            "NOT marketing_consent OR (marketing_consent_at IS NOT NULL AND consent_version IS NOT NULL AND length(trim(consent_version)) > 0)",
        )


def downgrade() -> None:
    # These columns and indexes are part of the enterprise baseline on current
    # deployments; never remove consent or attribution data during downgrade.
    return
