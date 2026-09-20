"""create the runtime lead-magnet table used by the public funnel service."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "029_funnel_lead_magnet_runtime_table"
down_revision: str | Sequence[str] | None = "028_order_stripe_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("funnel_lead_magnets"):
        return
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "funnel_lead_magnets",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("target_product_id", uuid_type, nullable=True),
        sa.Column("promise", sa.Text(), nullable=True),
        sa.Column("file_url", sa.String(length=500), nullable=True),
        sa.Column("landing_page_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("opt_in_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_product_id"], ["digital_products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_lead_magnet_status",
        ),
        sa.CheckConstraint(
            "opt_in_count >= 0",
            name="ck_lead_magnet_opt_in_count_non_negative",
        ),
    )
    op.create_index(
        "ix_funnel_lead_magnets_org_slug",
        "funnel_lead_magnets",
        ["organization_id", "slug"],
        unique=True,
    )
    op.create_index(
        "ix_funnel_lead_magnets_target_product_id",
        "funnel_lead_magnets",
        ["target_product_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("funnel_lead_magnets"):
        op.drop_index(
            "ix_funnel_lead_magnets_target_product_id",
            table_name="funnel_lead_magnets",
        )
        op.drop_index(
            "ix_funnel_lead_magnets_org_slug",
            table_name="funnel_lead_magnets",
        )
        op.drop_table("funnel_lead_magnets")
