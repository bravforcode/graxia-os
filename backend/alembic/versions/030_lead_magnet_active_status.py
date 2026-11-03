"""allow active lead magnets in the runtime lead-magnet table."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "030_lead_magnet_active_status"
down_revision: str | Sequence[str] | None = "029_funnel_lead_magnet_runtime_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_status_constraint(allowed_statuses: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("funnel_lead_magnets"):
        return

    existing = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints("funnel_lead_magnets")
    }
    with op.batch_alter_table("funnel_lead_magnets") as batch_op:
        for name in ("ck_lead_magnet_status", "ck_lead_magnet_runtime_status"):
            if name in existing:
                batch_op.drop_constraint(name, type_="check")
        batch_op.create_check_constraint(
            "ck_lead_magnet_status",
            f"status IN ({allowed_statuses})",
        )


def upgrade() -> None:
    _replace_status_constraint("'draft', 'active', 'published', 'archived'")


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("funnel_lead_magnets"):
        return
    # ``active`` was introduced by this revision. Normalize it to the
    # historical public state before restoring the old constraint.
    op.execute(
        sa.text(
            "UPDATE funnel_lead_magnets "
            "SET status = 'published' WHERE status = 'active'"
        )
    )
    _replace_status_constraint("'draft', 'published', 'archived'")
