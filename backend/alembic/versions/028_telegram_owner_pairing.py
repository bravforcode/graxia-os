"""Add tenant-bound Telegram owner pairing records.

Revision ID: 028_telegram_owner_pairing
Revises: 027_normalized_user_email
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "028_telegram_owner_pairing"
down_revision: str | Sequence[str] | None = "027_normalized_user_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_pairing_challenges",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_telegram_pairing_challenges_token_hash"),
    )
    op.create_index(
        "ix_telegram_pairing_challenges_organization_id",
        "telegram_pairing_challenges",
        ["organization_id"],
    )
    op.create_index(
        "ix_telegram_pairing_challenges_user_id",
        "telegram_pairing_challenges",
        ["user_id"],
    )

    op.create_table(
        "telegram_approval_bindings",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_approval_bindings_organization_id",
        "telegram_approval_bindings",
        ["organization_id"],
    )
    op.create_index(
        "uq_telegram_approval_bindings_active_telegram_user",
        "telegram_approval_bindings",
        ["telegram_user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_telegram_approval_bindings_active_user",
        "telegram_approval_bindings",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_telegram_approval_bindings_active_user",
        table_name="telegram_approval_bindings",
    )
    op.drop_index(
        "uq_telegram_approval_bindings_active_telegram_user",
        table_name="telegram_approval_bindings",
    )
    op.drop_index(
        "ix_telegram_approval_bindings_organization_id",
        table_name="telegram_approval_bindings",
    )
    op.drop_table("telegram_approval_bindings")
    op.drop_index(
        "ix_telegram_pairing_challenges_user_id",
        table_name="telegram_pairing_challenges",
    )
    op.drop_index(
        "ix_telegram_pairing_challenges_organization_id",
        table_name="telegram_pairing_challenges",
    )
    op.drop_table("telegram_pairing_challenges")
