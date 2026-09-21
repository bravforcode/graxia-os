"""align audit_log with the canonical audit query model."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "026_audit_query_contract"
down_revision: str | None = "031_align_lead_capture_runtime_fk"
branch_labels: str | None = None
depends_on: str | None = None


def _existing_columns(bind: sa.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table("audit_log"):
        return set()
    return {column["name"] for column in inspector.get_columns("audit_log")}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("audit_log"):
        return

    columns = {
        "organization_id": sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        "event_id": sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        "event_type": sa.Column("event_type", sa.String(length=100), nullable=True),
        "event_category": sa.Column(
            "event_category", sa.String(length=50), nullable=True
        ),
        "entity_type": sa.Column("entity_type", sa.String(length=100), nullable=True),
        "entity_id": sa.Column(
            "entity_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        "session_id": sa.Column("session_id", sa.String(length=64), nullable=True),
        "request_path": sa.Column(
            "request_path", sa.String(length=500), nullable=True
        ),
        "request_method": sa.Column(
            "request_method", sa.String(length=16), nullable=True
        ),
        "outcome": sa.Column("outcome", sa.String(length=20), nullable=True),
        "details": sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        "triggered_by": sa.Column(
            "triggered_by", sa.String(length=100), nullable=True
        ),
        "success": sa.Column("success", sa.Boolean(), nullable=True),
        "error_message": sa.Column("error_message", sa.Text(), nullable=True),
        "ai_model_used": sa.Column(
            "ai_model_used", sa.String(length=100), nullable=True
        ),
        "was_fallback": sa.Column("was_fallback", sa.Boolean(), nullable=True),
        "checksum": sa.Column("checksum", sa.String(length=64), nullable=True),
    }
    existing = _existing_columns(bind)
    for name, column in columns.items():
        if name not in existing:
            op.add_column("audit_log", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    for name in (
        "checksum",
        "was_fallback",
        "ai_model_used",
        "error_message",
        "success",
        "triggered_by",
        "details",
        "outcome",
        "request_method",
        "request_path",
        "session_id",
        "entity_id",
        "entity_type",
        "event_category",
        "event_type",
        "event_id",
        "organization_id",
    ):
        if name in existing:
            op.drop_column("audit_log", name)
