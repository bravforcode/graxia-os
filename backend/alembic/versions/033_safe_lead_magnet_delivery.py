"""Add explicit lead-magnet asset linkage and non-revenue comped orders."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "033_safe_lead_magnet_delivery"
down_revision: str | Sequence[str] | None = "032_skill_conversation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEAD_MAGNETS = "funnel_lead_magnets"
_ORDERS = "funnel_orders"
_ASSETS = "delivery_assets"
_ASSET_COLUMN = "delivery_asset_id"
_ASSET_INDEX = "ix_funnel_lead_magnets_delivery_asset_id"
_ASSET_FK = "fk_funnel_lead_magnets_delivery_asset_id"
_ORDER_STATUS_CHECK = "ck_order_status"
_OLD_ORDER_STATUS = "status IN ('pending', 'paid', 'failed', 'refunded', 'cancelled')"
_NEW_ORDER_STATUS = (
    "status IN ('pending', 'paid', 'comped', 'failed', 'refunded', 'cancelled')"
)


def _table_columns(bind: sa.engine.Connection, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    return (
        {column["name"] for column in inspector.get_columns(table)}
        if inspector.has_table(table)
        else set()
    )


def _has_asset_fk(bind: sa.engine.Connection) -> bool:
    return any(
        foreign_key.get("constrained_columns") == [_ASSET_COLUMN]
        and foreign_key.get("referred_table") == _ASSETS
        for foreign_key in sa.inspect(bind).get_foreign_keys(_LEAD_MAGNETS)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LEAD_MAGNETS) or not inspector.has_table(_ASSETS):
        raise RuntimeError("lead-magnet delivery prerequisites are missing")
    if not inspector.has_table(_ORDERS):
        raise RuntimeError("funnel_orders is missing")

    magnet_columns = _table_columns(bind, _LEAD_MAGNETS)
    magnet_indexes = {
        index["name"] for index in inspector.get_indexes(_LEAD_MAGNETS)
    }
    add_asset_column = _ASSET_COLUMN not in magnet_columns
    add_asset_fk = not _has_asset_fk(bind)
    add_asset_index = _ASSET_INDEX not in magnet_indexes
    if add_asset_column or add_asset_fk:
        with op.batch_alter_table(_LEAD_MAGNETS) as batch_op:
            if add_asset_column:
                batch_op.add_column(
                    sa.Column(_ASSET_COLUMN, postgresql.UUID(as_uuid=True), nullable=True)
                )
            if add_asset_fk:
                batch_op.create_foreign_key(
                    _ASSET_FK,
                    _ASSETS,
                    [_ASSET_COLUMN],
                    ["id"],
                    ondelete="SET NULL",
                )
    if add_asset_index:
        op.create_index(_ASSET_INDEX, _LEAD_MAGNETS, [_ASSET_COLUMN])

    order_checks = {
        constraint["name"]: constraint.get("sqltext", "")
        for constraint in inspector.get_check_constraints(_ORDERS)
        if constraint.get("name") == _ORDER_STATUS_CHECK
    }
    current_check = order_checks.get(_ORDER_STATUS_CHECK, "")
    if "comped" not in current_check:
        with op.batch_alter_table(_ORDERS) as batch_op:
            if current_check:
                batch_op.drop_constraint(_ORDER_STATUS_CHECK, type_="check")
            batch_op.create_check_constraint(_ORDER_STATUS_CHECK, _NEW_ORDER_STATUS)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    order_checks: dict[str, str] = {}
    if inspector.has_table(_ORDERS):
        order_checks = {
            constraint["name"]: constraint.get("sqltext", "")
            for constraint in inspector.get_check_constraints(_ORDERS)
            if constraint.get("name") == _ORDER_STATUS_CHECK
        }
        if "comped" in order_checks.get(_ORDER_STATUS_CHECK, ""):
            comped_orders = bind.execute(
                sa.text("SELECT count(*) FROM funnel_orders WHERE status = 'comped'")
            ).scalar_one()
            if comped_orders:
                raise RuntimeError("cannot downgrade while comped orders exist")

    magnet_columns = _table_columns(bind, _LEAD_MAGNETS)
    if _ASSET_COLUMN in magnet_columns:
        referenced_assets = bind.execute(
            sa.text(
                "SELECT count(*) FROM funnel_lead_magnets "
                "WHERE delivery_asset_id IS NOT NULL"
            )
        ).scalar_one()
        if referenced_assets:
            raise RuntimeError(
                "cannot downgrade while lead magnets reference delivery assets"
            )

    if "comped" in order_checks.get(_ORDER_STATUS_CHECK, ""):
        with op.batch_alter_table(_ORDERS) as batch_op:
            batch_op.drop_constraint(_ORDER_STATUS_CHECK, type_="check")
            batch_op.create_check_constraint(_ORDER_STATUS_CHECK, _OLD_ORDER_STATUS)

    if _ASSET_COLUMN not in magnet_columns:
        return

    magnet_indexes = {
        index["name"] for index in inspector.get_indexes(_LEAD_MAGNETS)
    }
    with op.batch_alter_table(_LEAD_MAGNETS) as batch_op:
        if _has_asset_fk(bind):
            foreign_keys = sa.inspect(bind).get_foreign_keys(_LEAD_MAGNETS)
            fk_name = next(
                foreign_key["name"]
                for foreign_key in foreign_keys
                if foreign_key.get("constrained_columns") == [_ASSET_COLUMN]
                and foreign_key.get("referred_table") == _ASSETS
            )
            if fk_name:
                batch_op.drop_constraint(fk_name, type_="foreignkey")
        if _ASSET_INDEX in magnet_indexes:
            batch_op.drop_index(_ASSET_INDEX)
        batch_op.drop_column(_ASSET_COLUMN)
