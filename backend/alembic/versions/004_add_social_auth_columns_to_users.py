"""add social auth columns to users

Revision ID: 004_users_social_cols
Revises: 003_fix_users_table
Create Date: 2026-04-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004_users_social_cols"
down_revision: str | None = "003_fix_users_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'users'
            ) THEN
                ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS provider VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS provider_id VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(1024);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'users'
            ) THEN
                ALTER TABLE users
                    DROP COLUMN IF EXISTS avatar_url,
                    DROP COLUMN IF EXISTS provider_id,
                    DROP COLUMN IF EXISTS provider;
            END IF;
        END
        $$;
        """
    )
