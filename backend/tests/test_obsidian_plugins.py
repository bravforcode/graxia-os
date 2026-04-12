"""Tests for Obsidian plugin manifest generation and Templater templates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.integrations.obsidian_plugins import write_plugin_manifest, write_vault_templates


# Skip permission tests on Windows due to permission model differences
pytestmark = pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="POSIX permission tests not reliable on Windows",
)


@pytest.mark.asyncio
async def test_write_plugin_manifest_creates_directory(tmp_path: Path):
    """Test that write_plugin_manifest creates .obsidian directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_plugin_manifest(vault)
    assert (vault / ".obsidian" / "community-plugins.json").exists()


@pytest.mark.asyncio
async def test_write_plugin_manifest_includes_required_plugins(tmp_path: Path):
    """Test that write_plugin_manifest includes all required plugins."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_plugin_manifest(vault)

    plugins_file = vault / ".obsidian" / "community-plugins.json"
    content = json.loads(plugins_file.read_text(encoding="utf-8"))

    required = {
        "dataview",
        "obsidian-tasks-plugin",
        "calendar",
        "templater-obsidian",
        "obsidian-git",
        "obsidian-kanban",
        "advanced-tables-obsidian",
        "obsidian-style-settings",
    }
    assert required.issubset(set(content))


@pytest.mark.asyncio
async def test_write_plugin_manifest_creates_app_config(tmp_path: Path):
    """Test that write_plugin_manifest creates app.json with default config."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_plugin_manifest(vault)

    app_file = vault / ".obsidian" / "app.json"
    assert app_file.exists()
    content = json.loads(app_file.read_text(encoding="utf-8"))
    assert content["legacyEditor"] is False
    assert content["livePreview"] is True
    assert "tabSize" in content


@pytest.mark.asyncio
async def test_write_plugin_manifest_creates_hotkeys_config(tmp_path: Path):
    """Test that write_plugin_manifest creates hotkeys.json."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_plugin_manifest(vault)

    hotkeys_file = vault / ".obsidian" / "hotkeys.json"
    assert hotkeys_file.exists()
    content = json.loads(hotkeys_file.read_text(encoding="utf-8"))
    assert isinstance(content, dict)


@pytest.mark.asyncio
async def test_write_vault_templates_creates_templates_folder(tmp_path: Path):
    """Test that write_vault_templates creates templates directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_vault_templates(vault)

    templates_dir = vault / "System" / "Templates"
    assert templates_dir.exists()
    assert templates_dir.is_dir()


@pytest.mark.asyncio
async def test_write_vault_templates_writes_template_files(tmp_path: Path):
    """Test that write_vault_templates writes template files."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_vault_templates(vault)

    templates_dir = vault / "System" / "Templates"
    # Should have at least some template files
    template_files = list(templates_dir.glob("*.md"))
    assert len(template_files) > 0


@pytest.mark.asyncio
async def test_write_vault_templates_contains_daily_note_template(tmp_path: Path):
    """Test that daily note template is created with expected structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_vault_templates(vault)

    daily_template = vault / "System" / "Templates" / "daily-note-template.md"
    assert daily_template.exists()
    content = daily_template.read_text(encoding="utf-8")
    assert "# Daily Note" in content or "Daily" in content


@pytest.mark.asyncio
async def test_write_vault_templates_preserves_existing_templates(tmp_path: Path):
    """Test that write_vault_templates doesn't overwrite existing templates."""
    vault = tmp_path / "vault"
    vault.mkdir()
    templates_dir = vault / "System" / "Templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Create an existing template
    existing_file = templates_dir / "custom-template.md"
    custom_content = "# Custom Template\nThis is custom content"
    existing_file.write_text(custom_content, encoding="utf-8")

    # Run write_vault_templates
    await write_vault_templates(vault)

    # Verify custom template is preserved
    assert existing_file.read_text(encoding="utf-8") == custom_content


@pytest.mark.asyncio
async def test_write_plugin_manifest_handles_permission_error(tmp_path: Path):
    """Test that write_plugin_manifest raises OSError on permission denied."""
    vault = tmp_path / "vault"
    vault.mkdir()
    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir()

    # Make read-only to prevent writes
    obsidian_dir.chmod(0o444)

    try:
        with pytest.raises(OSError):
            await write_plugin_manifest(vault)
    finally:
        # Restore permissions for cleanup
        obsidian_dir.chmod(0o755)


@pytest.mark.asyncio
async def test_write_vault_templates_handles_permission_error(tmp_path: Path):
    """Test that write_vault_templates raises OSError on permission denied."""
    vault = tmp_path / "vault"
    vault.mkdir()
    templates_dir = vault / "System" / "Templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Make read-only to prevent writes
    templates_dir.chmod(0o444)

    try:
        with pytest.raises(OSError):
            await write_vault_templates(vault)
    finally:
        # Restore permissions for cleanup
        templates_dir.chmod(0o755)
