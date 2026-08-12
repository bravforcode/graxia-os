"""Smoke test for Alembic migrations.

Verifies that Alembic can connect to the database configured via DATABASE_URL and
successfully run upgrade / downgrade for the initial migration.
"""
import os

import pytest


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping migration smoke test",
)
class TestMigrationsSmoke:
    def test_alembic_upgrade_and_downgrade(self):
        from alembic.config import Config
        from alembic import command

        cfg = Config("alembic.ini")
        # Ensure the env.py normalizes the asyncpg URL to a synchronous driver.
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
