"""add safe referral loop ledger."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "025_growth_referral"
down_revision: str | Sequence[str] | None = "025_conversion_event_touch_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)

    op.create_table(
        "referral_partners",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("user_id", uuid_type, nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False, server_default="0.20"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'suspended')",
            name="ck_referral_partner_status",
        ),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_referral_partner_commission_rate",
        ),
    )
    op.create_index(
        "ix_referral_partners_org_status",
        "referral_partners",
        ["organization_id", "status"],
    )
    op.create_index("ix_referral_partners_user_id", "referral_partners", ["user_id"])

    op.create_table(
        "referral_codes",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", uuid_type, nullable=False),
        sa.Column("issuer_user_id", uuid_type, nullable=True),
        sa.Column("owner_identity_hash", sa.String(length=64), nullable=True),
        sa.Column("partner_id", uuid_type, nullable=True),
        sa.Column("audience", sa.String(length=30), nullable=False),
        sa.Column("redirect_path", sa.String(length=500), nullable=False),
        sa.Column("bonus_asset_path", sa.String(length=500), nullable=True),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False, server_default="0.00"),
        sa.Column("hold_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["referral_partners.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_referral_codes_code_hash"),
        sa.CheckConstraint(
            "source_type IN ('captured_lead', 'verified_delivery', 'approved_partner')",
            name="ck_referral_code_source_type",
        ),
        sa.CheckConstraint(
            "audience IN ('regular_user', 'partner')",
            name="ck_referral_code_audience",
        ),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_referral_code_commission_rate",
        ),
    )
    op.create_index("ix_referral_codes_org_active", "referral_codes", ["organization_id", "is_active"])
    op.create_index("ix_referral_codes_owner_identity_hash", "referral_codes", ["owner_identity_hash"])
    op.create_index("ix_referral_codes_partner_id", "referral_codes", ["partner_id"])

    op.create_table(
        "referral_attributions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("referral_code_id", uuid_type, nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("identity_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referral_code_id"], ["referral_codes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "session_id", name="uq_referral_attribution_org_session"
        ),
    )
    op.create_index("ix_referral_attributions_code", "referral_attributions", ["referral_code_id"])

    op.create_table(
        "referral_conversions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("referral_code_id", uuid_type, nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("conversion_key", sa.String(length=255), nullable=False),
        sa.Column("verified_order_id", uuid_type, nullable=False),
        sa.Column("reward_type", sa.String(length=30), nullable=False),
        sa.Column("bonus_asset_path", sa.String(length=500), nullable=True),
        sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False, server_default="0.00"),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="eligible"),
        sa.Column("settlement_status", sa.String(length=30), nullable=False, server_default="not_applicable"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referral_code_id"], ["referral_codes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_code_id", name="uq_referral_conversion_code"),
        sa.UniqueConstraint(
            "organization_id", "conversion_key", name="uq_referral_conversion_key"
        ),
        sa.CheckConstraint(
            "reward_type IN ('regular_bonus', 'partner_commission')",
            name="ck_referral_conversion_reward_type",
        ),
        sa.CheckConstraint(
            "settlement_status IN ('not_applicable', 'manual_pending', 'manual_settled', 'reversed')",
            name="ck_referral_conversion_settlement_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("referral_conversions")
    op.drop_index("ix_referral_attributions_code", table_name="referral_attributions")
    op.drop_table("referral_attributions")
    op.drop_index("ix_referral_codes_partner_id", table_name="referral_codes")
    op.drop_index("ix_referral_codes_owner_identity_hash", table_name="referral_codes")
    op.drop_index("ix_referral_codes_org_active", table_name="referral_codes")
    op.drop_table("referral_codes")
    op.drop_index("ix_referral_partners_user_id", table_name="referral_partners")
    op.drop_index("ix_referral_partners_org_status", table_name="referral_partners")
    op.drop_table("referral_partners")
