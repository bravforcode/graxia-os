"""allow active lead magnets in the runtime lead-magnet table."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "030_lead_magnet_active_status"
down_revision: str | Sequence[str] | None = "029_funnel_lead_magnet_runtime_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("funnel_lead_magnets") as batch_op:
        batch_op.drop_constraint("ck_lead_magnet_status", type_="check")
        batch_op.create_check_constraint(
            "ck_lead_magnet_status",
            "status IN ('draft', 'active', 'published', 'archived')",
        )


def downgrade() -> None:
    with op.batch_alter_table("funnel_lead_magnets") as batch_op:
        batch_op.drop_constraint("ck_lead_magnet_status", type_="check")
        batch_op.create_check_constraint(
            "ck_lead_magnet_status",
            "status IN ('draft', 'published', 'archived')",
        )
