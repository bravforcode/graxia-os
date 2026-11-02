"""Add CHECK constraints for status/type fields

Revision ID: 016_add_check_constraints
Revises: d5bb1ddf06e3
Create Date: 2026-04-30
"""

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_check_constraints"
down_revision: str = "d5bb1ddf06e3"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    return any(
        constraint.get("name") == constraint_name
        for constraint in sa.inspect(bind).get_check_constraints(table_name)
    )


def _create_check_constraint_if_missing(
    bind, name: str, table_name: str, condition: str
) -> None:
    if not _constraint_exists(bind, table_name, name):
        op.create_check_constraint(name, table_name, condition)


def upgrade() -> None:
    if not _is_postgres():
        return  # SQLite CHECK constraints are added at table creation; skip on test DB

    bind = op.get_bind()

    # ── submissions ──────────────────────────────────────────────────────────
    _create_check_constraint_if_missing(
        bind,
        "ck_submission_status",
        "submissions",
        "status IN ('draft','sent','viewed','replied','won','lost','withdrawn')",
    )
    _create_check_constraint_if_missing(
        bind,
        "ck_submission_type",
        "submissions",
        "type IN ('proposal','bid','application','email','message','other')",
    )

    # ── contacts ─────────────────────────────────────────────────────────────
    _create_check_constraint_if_missing(
        bind,
        "ck_contact_relationship_strength",
        "contacts",
        "relationship_strength BETWEEN 1 AND 5 OR relationship_strength IS NULL",
    )

    # ── content_drafts ───────────────────────────────────────────────────────
    _create_check_constraint_if_missing(
        bind,
        "ck_draft_status",
        "content_drafts",
        "status IN ('pending','approved','rejected','sent')",
    )

    # ── approval_requests ────────────────────────────────────────────────────
    _create_check_constraint_if_missing(
        bind,
        "ck_approval_status",
        "approval_requests",
        "status IN ('pending','approved','rejected','expired')",
    )

    # ── users ────────────────────────────────────────────────────────────────
    _create_check_constraint_if_missing(
        bind,
        "ck_user_role",
        "users",
        "role IN ('viewer','user','operator','admin')",
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.drop_constraint("ck_user_role", "users", type_="check")
    op.drop_constraint("ck_approval_status", "approval_requests", type_="check")
    op.drop_constraint("ck_draft_status", "content_drafts", type_="check")
    op.drop_constraint("ck_contact_relationship_strength", "contacts", type_="check")
    op.drop_constraint("ck_submission_type", "submissions", type_="check")
    op.drop_constraint("ck_submission_status", "submissions", type_="check")
