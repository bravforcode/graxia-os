import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agents.vault_reader import VaultReaderAgent


async def test_invalid_filename_is_counted_and_logged_without_raising(caplog):
    changed = [{"file_path": Path("OPP-not-a-uuid.md"), "status": "scored"}]

    with patch(
        "app.integrations.obsidian.scan_changed_opportunity_files", return_value=changed
    ), patch.object(VaultReaderAgent, "log_audit", new=AsyncMock()), caplog.at_level(
        logging.WARNING, logger="app.agents.vault_reader"
    ):
        result = await VaultReaderAgent().sync_vault_changes(vault_path="/vault")

    assert result == {"synced_count": 0, "failed_count": 1}
    assert "vault_reader_invalid_filename" in caplog.text
    assert "filename=OPP-not-a-uuid" in caplog.text
