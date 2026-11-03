"""persist first and last touch attribution on conversion events."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "025_conversion_event_touch_attribution"
down_revision: str | Sequence[str] | None = "024_organic_attribution_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Older installations created Alembic's version column as varchar(32),
    # while the growth migrations use longer, descriptive revision IDs.
    # Expand it before Alembic records this revision so the upgrade can be
    # applied atomically on those databases.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    version_columns = (
        {
            column["name"]: column
            for column in inspector.get_columns("alembic_version")
        }
        if inspector.has_table("alembic_version")
        else {}
    )
    version_column = version_columns.get("version_num")
    current_length = getattr(version_column.get("type"), "length", None) if version_column else None
    if current_length is not None and current_length < 64:
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=current_length),
            type_=sa.String(length=64),
            existing_nullable=False,
        )

    columns = (
        ("first_touch_source", sa.String(length=100)),
        ("first_touch_medium", sa.String(length=100)),
        ("first_touch_campaign", sa.String(length=100)),
        ("first_touch_referrer", sa.Text()),
        ("first_touch_path", sa.String(length=500)),
        ("last_touch_source", sa.String(length=100)),
        ("last_touch_medium", sa.String(length=100)),
        ("last_touch_campaign", sa.String(length=100)),
        ("last_touch_referrer", sa.Text()),
        ("last_touch_path", sa.String(length=500)),
        ("landing_path", sa.String(length=500)),
        ("content_id", sa.String(length=255)),
        ("referral_code", sa.String(length=160)),
    )
    inspector = sa.inspect(bind)
    if not inspector.has_table("conversion_events"):
        return
    existing_columns = {
        column["name"] for column in inspector.get_columns("conversion_events")
    }
    for name, column_type in columns:
        if name not in existing_columns:
            op.add_column("conversion_events", sa.Column(name, column_type, nullable=True))
            existing_columns.add(name)


def downgrade() -> None:
    # Attribution columns are part of the baseline on current deployments;
    # preserve historical attribution during downgrade.
    return
