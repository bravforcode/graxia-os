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
    op.add_column(
        "conversion_events",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "uq_conversion_events_org_idempotency",
        "conversion_events",
        ["organization_id", "idempotency_key"],
        unique=True,
    )
    op.add_column(
        "contacts",
        sa.Column(
            "marketing_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "contacts",
        sa.Column("marketing_consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("consent_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "marketing_unsubscribed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "contacts",
        sa.Column("marketing_unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_contact_marketing_consent_audit",
        "contacts",
        "NOT marketing_consent OR (marketing_consent_at IS NOT NULL AND consent_version IS NOT NULL AND length(trim(consent_version)) > 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contact_marketing_consent_audit", "contacts", type_="check")
    op.drop_column("contacts", "marketing_unsubscribed_at")
    op.drop_column("contacts", "marketing_unsubscribed")
    op.drop_column("contacts", "consent_version")
    op.drop_column("contacts", "marketing_consent_at")
    op.drop_column("contacts", "marketing_consent")
    op.drop_index("uq_conversion_events_org_idempotency", table_name="conversion_events")
    op.drop_column("conversion_events", "idempotency_key")
