"""add verified Revenue OS bridge evidence."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "026_revenue_bridge"
down_revision: str | Sequence[str] | None = "025_growth_referral"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revenue_bridge_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_kind", sa.String(length=50), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="THB"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column(
            "signature_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("normalized_status", sa.String(length=20), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_revenue_bridge_provider_event",
        ),
        sa.CheckConstraint(
            "event_kind IN ('subscription_activated', 'subscription_cancelled', 'payment_failed', 'refund')",
            name="ck_revenue_bridge_event_kind",
        ),
        sa.CheckConstraint(
            "plan IN ('starter', 'growth', 'scale')",
            name="ck_revenue_bridge_plan",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_revenue_bridge_amount_non_negative"),
        sa.CheckConstraint("currency = 'THB'", name="ck_revenue_bridge_currency_thb"),
        sa.CheckConstraint(
            "normalized_status IN ('active', 'canceled', 'past_due', 'refunded')",
            name="ck_revenue_bridge_normalized_status",
        ),
    )
    op.create_index(
        "ix_revenue_bridge_events_provider",
        "revenue_bridge_events",
        ["provider"],
    )
    op.create_index(
        "ix_revenue_bridge_events_organization_id",
        "revenue_bridge_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_revenue_bridge_events_event_kind",
        "revenue_bridge_events",
        ["event_kind"],
    )
    op.create_index(
        "ix_revenue_bridge_org_occurred",
        "revenue_bridge_events",
        ["organization_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_revenue_bridge_org_occurred", table_name="revenue_bridge_events")
    op.drop_index("ix_revenue_bridge_events_event_kind", table_name="revenue_bridge_events")
    op.drop_index(
        "ix_revenue_bridge_events_organization_id", table_name="revenue_bridge_events"
    )
    op.drop_index("ix_revenue_bridge_events_provider", table_name="revenue_bridge_events")
    op.drop_table("revenue_bridge_events")
