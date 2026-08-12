"""fix users table schema

The public.users table was created by a different system and has an
incompatible schema (integer PK, password, username, auth_id, etc.).
create_all silently skipped it because the table already existed.
This migration drops the old table and creates the correct one.

Revision ID: 003_fix_users_table
Revises: 002_schema_reconciliation
Create Date: 2026-04-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_fix_users_table"
down_revision: str | None = "002_schema_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"]: c for c in inspector.get_columns("users")}

    # Check if users table already looks like our modern UUID-based table
    # from Base.metadata.create_all (happens on fresh Supabase installs)
    if "id" in columns and str(columns["id"]["type"]) == "UUID":
        print("💡 Users table already has UUID schema, skipping recreation.")
        return

    # Rename the old incompatible table for safety rather than dropping it
    op.execute("ALTER TABLE users RENAME TO users_legacy_incompatible")

    # Create the correct users table
    op.execute(
        """
        CREATE TABLE users (
            id          UUID PRIMARY KEY,
            email       VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            full_name   VARCHAR(255),
            role        VARCHAR(50) NOT NULL DEFAULT 'user',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at TIMESTAMP WITH TIME ZONE,
            totp_secret VARCHAR(128),
            totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at  TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_users_email ON users (email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("ALTER TABLE users_legacy_incompatible RENAME TO users")
