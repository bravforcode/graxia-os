"""Smoke test for Alembic migrations.

Verifies that Alembic can connect to the database configured via DATABASE_URL and
successfully run upgrade / downgrade for the initial migration.
"""

import os

import pytest


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="DATABASE_URL not set or sqlite default; skipping migration smoke test",
)
class TestMigrationsSmoke:
    def test_alembic_upgrade_and_downgrade(self):
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        # Ensure the env.py normalizes the asyncpg URL to a synchronous driver.
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
