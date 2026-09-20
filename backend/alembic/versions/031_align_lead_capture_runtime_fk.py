"""align lead captures with the runtime lead-magnet table."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "031_align_lead_capture_runtime_fk"
down_revision: str | Sequence[str] | None = "030_lead_magnet_active_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUNTIME_FK_NAME = "fk_lead_captures_funnel_lead_magnet_id"
_LEGACY_FK_NAME = "fk_lead_captures_lead_magnet_id_legacy"


def _table_exists(bind: sa.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _copy_referenced_magnets(
    bind: sa.Connection, source: str, target: str, *, reverse: bool = False
) -> None:
    if not _table_exists(bind, source) or not _table_exists(bind, target):
        return

    inspector = sa.inspect(bind)
    source_columns = {column["name"] for column in inspector.get_columns(source)}
    target_columns = {column["name"] for column in inspector.get_columns(target)}
    required = {
        "id",
        "organization_id",
        "slug",
        "title" if not reverse else "name",
        "description" if not reverse else "promise",
        "status",
    }
    if not required <= source_columns or not required - {"title", "description", "name", "promise"} <= target_columns:
        return

    title_column = "name" if reverse else "title"
    description_column = "promise" if reverse else "description"
    target_title_column = "title" if reverse else "name"
    target_description_column = "description" if reverse else "promise"
    bind.execute(
        sa.text(
            f"""
            INSERT INTO {target}
                (id, organization_id, slug, {target_title_column},
                 {target_description_column}, status)
            SELECT source.id, source.organization_id, source.slug,
                   source.{title_column}, source.{description_column}, source.status
            FROM {source} AS source
            JOIN (
                SELECT DISTINCT lead_magnet_id
                FROM lead_captures
                WHERE lead_magnet_id IS NOT NULL
            ) AS captures ON captures.lead_magnet_id = source.id
            WHERE NOT EXISTS (
                SELECT 1 FROM {target} AS existing WHERE existing.id = source.id
            )
            """
        )
    )


def _replace_fk(bind: sa.Connection, target: str, name: str) -> None:
    if not _table_exists(bind, "lead_captures") or not _table_exists(bind, target):
        return

    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("lead_captures")
    lead_magnet_fks = [
        fk
        for fk in foreign_keys
        if fk.get("constrained_columns") == ["lead_magnet_id"]
    ]
    if any(fk.get("name") == name for fk in lead_magnet_fks):
        return

    if bind.dialect.name == "sqlite":
        metadata = sa.MetaData()
        captures = sa.Table("lead_captures", metadata, autoload_with=bind)
        for constraint in list(captures.constraints):
            if not isinstance(constraint, sa.ForeignKeyConstraint):
                continue
            if {column.name for column in constraint.columns} == {"lead_magnet_id"}:
                captures.constraints.remove(constraint)
        captures.append_constraint(
            sa.ForeignKeyConstraint(
                ["lead_magnet_id"], [f"{target}.id"], name=name
            )
        )
        with op.batch_alter_table(
            "lead_captures", copy_from=captures, recreate="always"
        ):
            pass
        return

    for foreign_key in lead_magnet_fks:
        if foreign_key.get("referred_table") == "lead_magnets" and foreign_key.get("name"):
            op.drop_constraint(
                foreign_key["name"], "lead_captures", type_="foreignkey"
            )
    if not any(
        foreign_key.get("referred_table") == target
        and foreign_key.get("name") == name
        for foreign_key in sa.inspect(bind).get_foreign_keys("lead_captures")
    ):
        op.create_foreign_key(
            name,
            "lead_captures",
            target,
            ["lead_magnet_id"],
            ["id"],
        )


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "lead_captures") or not _table_exists(
        bind, "funnel_lead_magnets"
    ):
        return
    _copy_referenced_magnets(bind, "lead_magnets", "funnel_lead_magnets")
    _replace_fk(bind, "funnel_lead_magnets", _RUNTIME_FK_NAME)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "lead_captures") or not _table_exists(
        bind, "lead_magnets"
    ):
        return
    _copy_referenced_magnets(
        bind, "funnel_lead_magnets", "lead_magnets", reverse=True
    )
    _replace_fk(bind, "lead_magnets", _LEGACY_FK_NAME)
