import logging
from unittest.mock import AsyncMock, patch

from app.tasks.vault_sync import run_vault_sync


async def test_run_vault_sync_returns_counts_and_logs_them(caplog):
    agent = AsyncMock()
    agent.sync_vault_changes.return_value = {"synced_count": 2, "failed_count": 1}

    with caplog.at_level(logging.INFO, logger="app.tasks.vault_sync"), patch(
        "app.agents.vault_reader.VaultReaderAgent", return_value=agent
    ):
        result = await run_vault_sync()

    assert result == {"synced_count": 2, "failed_count": 1}
    assert "vault_sync_complete" in caplog.text
    assert "synced_count=2" in caplog.text
