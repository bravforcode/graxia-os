"""Obsidian plugin manifest generation and Templater template setup."""
import asyncio
import json
from pathlib import Path
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)

# Required plugins for the Obsidian vault
REQUIRED_PLUGINS = [
    "dataview",
    "obsidian-tasks-plugin",
    "calendar",
    "templater-obsidian",
    "obsidian-git",
    "obsidian-kanban",
    "advanced-tables-obsidian",
    "obsidian-style-settings",
]

# Placeholder for plugin hotkeys configuration
PLUGIN_HOTKEYS: dict = {}

# Default Obsidian app configuration
DEFAULT_APP_CONFIG = {
    "legacyEditor": False,
    "livePreview": True,
    "defaultViewMode": "source",
    "vimMode": False,
    "tabSize": 2,
    "useMarkdownLinks": False,
    "showLineNumber": True,
}

# Template definitions for Templater
TEMPLATE_DEFINITIONS = {
    "daily-note-template.md": """# Daily Note - <% tp.date.now("YYYY-MM-DD") %>

## Focus
<% tp.file.cursor() %>

## Wins
-

## Open Loops
-

## Decisions
-

## Notes
""",
    "weekly-review-template.md": """# Weekly Review - <% tp.date.now("gggg-[W]ww") %>

## Metrics
- Opportunities:
- Submissions:
- Wins:
- Losses:

## Highlights
<% tp.file.cursor() %>

## Learnings
-

## Next Week Focus
-
""",
    "project-note-template.md": """---
type: project
created: <% tp.date.now("YYYY-MM-DD HH:mm:ss") %>
---

# <% tp.file.title %>

## Overview
<% tp.file.cursor() %>

## Status
- Current Phase:
- Progress:

## Key Results
-

## Next Steps
-

## Notes
""",
    "contact-note-template.md": """---
type: contact
created: <% tp.date.now("YYYY-MM-DD HH:mm:ss") %>
---

# <% tp.file.title %>

## Contact Info
- Email:
- Company:
- Role:
- LinkedIn:

## Relationship
- Strength:
- Last Contacted:

## Notes
<% tp.file.cursor() %>

## History
-
""",
    "opportunity-note-template.md": """---
type: opportunity
created: <% tp.date.now("YYYY-MM-DD HH:mm:ss") %>
---

# <% tp.file.title %>

## Source
- Platform:
- URL:

## Status
- Status: new
- Score:
- Priority:
- Deadline:

## Description
<% tp.file.cursor() %>

## Analysis
""",
}


async def write_plugin_manifest(vault_path: Path) -> dict[str, Any]:
    """Write .obsidian/community-plugins.json and basic app config.

    Creates the Obsidian configuration directory and writes:
    - community-plugins.json: list of enabled plugin IDs
    - app.json: basic editor configuration
    - hotkeys.json: placeholder for plugin hotkeys

    Args:
        vault_path: Path to the Obsidian vault root directory

    Returns:
        Dictionary with result metadata including plugins_written and path

    Raises:
        OSError: If directory creation or file writes fail
    """
    obsidian_dir = vault_path / ".obsidian"

    try:
        await asyncio.to_thread(obsidian_dir.mkdir, parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            "obsidian_dir_creation_failed",
            path=str(obsidian_dir),
            error=str(e),
        )
        raise

    # community-plugins.json — list of enabled plugin IDs
    plugins_file = obsidian_dir / "community-plugins.json"
    plugins_content = json.dumps(REQUIRED_PLUGINS, indent=2)
    try:
        await asyncio.to_thread(
            plugins_file.write_text,
            plugins_content,
            encoding="utf-8",
        )
        logger.info(
            "obsidian_community_plugins_written",
            path=str(plugins_file),
            count=len(REQUIRED_PLUGINS),
        )
    except OSError as e:
        logger.error(
            "obsidian_community_plugins_write_failed",
            path=str(plugins_file),
            error=str(e),
        )
        raise

    # app.json — basic editor config
    app_file = obsidian_dir / "app.json"
    app_exists = await asyncio.to_thread(app_file.exists)
    if not app_exists:
        app_content = json.dumps(DEFAULT_APP_CONFIG, indent=2)
        try:
            await asyncio.to_thread(
                app_file.write_text,
                app_content,
                encoding="utf-8",
            )
            logger.info("obsidian_app_config_created", path=str(app_file))
        except OSError as e:
            logger.error(
                "obsidian_app_config_write_failed",
                path=str(app_file),
                error=str(e),
            )
            raise

    # hotkeys.json — empty placeholder
    hotkeys_file = obsidian_dir / "hotkeys.json"
    hotkeys_exists = await asyncio.to_thread(hotkeys_file.exists)
    if not hotkeys_exists:
        hotkeys_content = json.dumps(PLUGIN_HOTKEYS, indent=2)
        try:
            await asyncio.to_thread(
                hotkeys_file.write_text,
                hotkeys_content,
                encoding="utf-8",
            )
            logger.info("obsidian_hotkeys_config_created", path=str(hotkeys_file))
        except OSError as e:
            logger.error(
                "obsidian_hotkeys_config_write_failed",
                path=str(hotkeys_file),
                error=str(e),
            )
            raise

    return {
        "plugins_written": REQUIRED_PLUGINS,
        "path": str(plugins_file),
        "count": len(REQUIRED_PLUGINS),
    }


async def write_vault_templates(vault_path: Path) -> dict[str, Any]:
    """Write Templater template files to the vault.

    Creates System/Templates directory and writes template files for:
    - Daily notes
    - Weekly reviews
    - Project notes
    - Contact notes
    - Opportunity notes

    Does not overwrite existing template files.

    Args:
        vault_path: Path to the Obsidian vault root directory

    Returns:
        Dictionary with result metadata including templates_written and path

    Raises:
        OSError: If directory creation or file writes fail
    """
    templates_dir = vault_path / "System" / "Templates"

    try:
        await asyncio.to_thread(templates_dir.mkdir, parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            "obsidian_templates_dir_creation_failed",
            path=str(templates_dir),
            error=str(e),
        )
        raise

    templates_written = []
    for filename, content in TEMPLATE_DEFINITIONS.items():
        template_file = templates_dir / filename
        file_exists = await asyncio.to_thread(template_file.exists)
        if not file_exists:
            try:
                await asyncio.to_thread(
                    template_file.write_text,
                    content,
                    encoding="utf-8",
                )
                templates_written.append(filename)
                logger.info("obsidian_template_written", path=str(template_file))
            except OSError as e:
                logger.error(
                    "obsidian_template_write_failed",
                    path=str(template_file),
                    filename=filename,
                    error=str(e),
                )
                raise

    logger.info(
        "obsidian_templates_bootstrap",
        template_count=len(templates_written),
        path=str(templates_dir),
    )

    return {
        "templates_written": templates_written,
        "path": str(templates_dir),
        "count": len(templates_written),
    }
