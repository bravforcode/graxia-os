"""Add single-use organization invitations without changing existing accounts.

Revision ID: 039_invite_only_identity
Revises: 038_telegram_owner_pairing
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "039_invite_only_identity"
down_revision: str | Sequence[str] | None = "038_telegram_owner_pairing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_user_role_constraint() -> bool:
    return any(
        constraint["name"] == "ck_user_role"
        for constraint in sa.inspect(op.get_bind()).get_check_constraints("users")
    )


def _replace_user_role_constraint(*, allow_owner: bool) -> None:
    # The role check was installed only on PostgreSQL. Leave unconstrained
    # schemas alone rather than imposing a new restriction on existing accounts.
    if not _has_user_role_constraint():
        return
    roles = "'viewer','user','operator','admin'" + (",'owner'" if allow_owner else "")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.create_check_constraint("ck_user_role", f"role IN ({roles})")


def upgrade() -> None:
    _replace_user_role_constraint(allow_owner=True)
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("issued_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('operator', 'viewer')", name="ck_invitation_role"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_invitations_token_digest"),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])


def downgrade() -> None:
    if _has_user_role_constraint() and op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM users WHERE role = 'owner'")
    ):
        raise RuntimeError("Cannot downgrade identity while owner accounts exist; roles are preserved")
    _replace_user_role_constraint(allow_owner=False)
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_table("invitations")
