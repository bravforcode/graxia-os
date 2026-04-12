"""
Obsidian integration and second-brain automation.
"""
import asyncio
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import yaml
from structlog import get_logger

try:
    import aiofiles
except ModuleNotFoundError:
    class _AsyncFile:
        def __init__(self, path: Path, mode: str, encoding: str | None = None):
            self.path = path
            self.mode = mode
            self.encoding = encoding
            self._file = None

        async def __aenter__(self):
            def _open():
                return open(self.path, self.mode, encoding=self.encoding)

            self._file = await asyncio.to_thread(_open)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if self._file is not None:
                await asyncio.to_thread(self._file.close)

        async def write(self, data: str):
            await asyncio.to_thread(self._file.write, data)

        async def read(self) -> str:
            return await asyncio.to_thread(self._file.read)

    class _AiofilesFallback:
        @staticmethod
        def open(path: Path, mode: str, encoding: str | None = None):
            return _AsyncFile(path, mode, encoding)

    aiofiles = _AiofilesFallback()

from app.config import settings

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower())
    normalized = normalized.strip("-")
    return normalized or "untitled"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _normalize_frontmatter(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_frontmatter(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_frontmatter(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _render_frontmatter(frontmatter: dict[str, Any] | None) -> str:
    if not frontmatter:
        return ""
    serialized = yaml.safe_dump(
        _normalize_frontmatter(frontmatter),
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{serialized}\n---\n\n"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _folder_title(folder: str) -> str:
    return folder.replace("/", " / ")


class ObsidianConnector:
    """Connect to an Obsidian vault via filesystem or local REST API."""

    def __init__(
        self,
        vault_path: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        root_folder: str | None = None,
    ):
        self.vault_path = Path(vault_path) if vault_path else None
        self.api_url = api_url
        self.api_key = api_key
        self.root_folder = (root_folder or "").strip("/\\ ")
        self.client = httpx.AsyncClient(timeout=30.0) if api_url else None

    async def close(self):
        if self.client:
            await self.client.aclose()

    def _normalized_folder(self, folder: str = "") -> str:
        parts = [part.strip("/\\ ") for part in [self.root_folder, folder] if part and part.strip("/\\ ")]
        return "/".join(parts)

    def _resolved_directory(self, folder: str = "") -> Path:
        if not self.vault_path:
            raise ValueError("vault_path not configured")
        target_dir = self.vault_path
        normalized_folder = self._normalized_folder(folder)
        if normalized_folder:
            for part in normalized_folder.split("/"):
                target_dir /= part
        return target_dir

    def _note_path_hint(self, folder: str, filename: str) -> str:
        normalized_folder = self._normalized_folder(folder)
        return f"{normalized_folder}/{filename}.md" if normalized_folder else f"{filename}.md"

    async def write_note(
        self,
        filename: str,
        content: str,
        folder: str = "",
        frontmatter: dict[str, Any] | None = None,
        overwrite: bool = True,
    ) -> Path:
        full_content = f"{_render_frontmatter(frontmatter)}{content}"

        if self.vault_path:
            target_dir = self._resolved_directory(folder)
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"{filename}.md"
            if file_path.exists() and not overwrite:
                return file_path

            async with aiofiles.open(file_path, "w", encoding="utf-8") as file_handle:
                await file_handle.write(full_content)

            logger.info("obsidian_note_written", path=str(file_path))
            return file_path

        if self.client and self.api_url:
            if not overwrite:
                try:
                    await self.api_read_note(filename, folder)
                    return Path(self._note_path_hint(folder, filename))
                except Exception:
                    pass
            await self.api_create_note(filename, full_content, folder=folder)
            return Path(self._note_path_hint(folder, filename))

        raise ValueError("vault_path not configured")

    async def read_note(self, filename: str, folder: str = "") -> str:
        if self.vault_path:
            file_path = self._resolved_directory(folder) / f"{filename}.md"
            if not file_path.exists():
                raise FileNotFoundError(f"Note not found: {file_path}")

            async with aiofiles.open(file_path, "r", encoding="utf-8") as file_handle:
                return await file_handle.read()

        if self.client and self.api_url:
            return await self.api_read_note(filename, folder)

        raise ValueError("vault_path not configured")

    async def append_to_note(self, filename: str, content: str, folder: str = "") -> Path:
        if self.vault_path:
            target_dir = self._resolved_directory(folder)
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"{filename}.md"
            async with aiofiles.open(file_path, "a", encoding="utf-8") as file_handle:
                await file_handle.write(f"\n{content}")
            logger.info("obsidian_note_appended", path=str(file_path))
            return file_path

        if self.client and self.api_url:
            existing = ""
            try:
                existing = await self.api_read_note(filename, folder)
            except Exception:
                existing = ""
            await self.api_create_note(filename, f"{existing}\n{content}".strip(), folder=folder)
            return Path(self._note_path_hint(folder, filename))

        raise ValueError("vault_path not configured")

    async def list_notes(self, folder: str = "", pattern: str = "*.md") -> list[Path]:
        if not self.vault_path:
            raise ValueError("list_notes requires filesystem vault access")

        target_dir = self._resolved_directory(folder)
        if not target_dir.exists():
            return []
        return list(target_dir.glob(pattern))

    async def api_create_note(
        self,
        filename: str,
        content: str,
        folder: str = "",
    ) -> dict[str, Any]:
        if not self.client or not self.api_url:
            raise ValueError("API not configured")

        path = self._note_path_hint(folder, filename)
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await self.client.post(
            f"{self.api_url}/vault/{path}",
            json={"content": content},
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def api_read_note(self, filename: str, folder: str = "") -> str:
        if not self.client or not self.api_url:
            raise ValueError("API not configured")

        path = self._note_path_hint(folder, filename)
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await self.client.get(
            f"{self.api_url}/vault/{path}",
            headers=headers,
        )
        response.raise_for_status()
        return response.text

    async def _ensure_index(self, folder: str, title: str, intro: str) -> Path:
        content = f"# {title}\n\n{intro}\n"
        return await self.write_note(
            "Index",
            content,
            folder=folder,
            frontmatter={"type": "index", "folder": folder, "created": _utc_now().isoformat()},
            overwrite=False,
        )

    async def _ensure_unique_link(
        self,
        folder: str,
        filename: str,
        header: str,
        line: str,
        match_text: str,
    ) -> None:
        try:
            existing = await self.read_note(filename, folder=folder)
        except FileNotFoundError:
            existing = ""

        if existing:
            if match_text in existing:
                return
            await self.append_to_note(filename, line, folder=folder)
            return

        await self.write_note(filename, f"{header}\n\n{line}", folder=folder, overwrite=True)

    async def _append_activity(self, project_slug: str, title: str, details: str) -> None:
        folder = f"Projects/{project_slug}"
        timestamp = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
        line = f"- {timestamp} {title}: {details}"
        await self._ensure_unique_link(
            folder=folder,
            filename="Activity Log",
            header=f"# Activity Log - {project_slug}",
            line=line,
            match_text=line,
        )

    def _project_link(self, project_slug: str, label: str | None = None) -> str:
        text = label or project_slug
        return f"[[Projects/{project_slug}/Overview|{text}]]"

    async def ensure_project_workspace(self, project: dict[str, Any]) -> dict[str, str]:
        name = _stringify(project.get("name")) or "Untitled Project"
        slug = _slugify(name)
        tech_stack = [item for item in (_stringify(skill) for skill in _as_list(project.get("tech_stack"))) if item]
        best_for = [item for item in (_stringify(value) for value in _as_list(project.get("best_for"))) if item]

        overview = f"""# {name}

## Tagline
{_stringify(project.get("tagline")) or "No tagline yet."}

## Description
{_stringify(project.get("description")) or "No description yet."}

## Tech Stack
{", ".join(tech_stack) or "Not captured yet."}

## Links
- GitHub: {_stringify(project.get("github_url")) or "N/A"}
- Live: {_stringify(project.get("live_url")) or "N/A"}

## Best For
{", ".join(best_for) or "General"}
"""
        await self.write_note(
            "Overview",
            overview,
            folder=f"Projects/{slug}",
            frontmatter={
                "type": "project",
                "project_slug": slug,
                "project_name": name,
                "tech_stack": tech_stack,
                "best_for": best_for,
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )

        await self.write_note(
            "Context",
            (
                f"# Context - {name}\n\n"
                "## Current State\nUse `/obsidian/context` to capture decisions, architecture notes, and important context.\n"
            ),
            folder=f"Projects/{slug}",
            frontmatter={"type": "project-context", "project_slug": slug},
            overwrite=False,
        )
        await self.write_note(
            "Activity Log",
            f"# Activity Log - {name}\n\n## Timeline\n",
            folder=f"Projects/{slug}",
            frontmatter={"type": "project-activity", "project_slug": slug},
            overwrite=False,
        )
        await self.write_note(
            "Tasks",
            f"# Tasks - {name}\n\n## Open Tasks\n",
            folder=f"Projects/{slug}",
            frontmatter={"type": "project-tasks", "project_slug": slug},
            overwrite=False,
        )

        skill_lines = [
            f"- [[Skills/Technical/{_slugify(skill)}|{skill}]]"
            for skill in tech_stack
        ]
        await self.write_note(
            "Skills",
            (
                f"# Skills - {name}\n\n"
                "## Relevant Skills\n"
                f"{chr(10).join(skill_lines) if skill_lines else '- Capture relevant skills here.'}\n"
            ),
            folder=f"Projects/{slug}",
            frontmatter={"type": "project-skills", "project_slug": slug},
            overwrite=True,
        )
        await self.write_note(
            "Index",
            (
                f"# {name} Context Index\n\n"
                "## Captured Context\n"
                "- Use `/obsidian/context` to add structured decision and delivery notes.\n"
            ),
            folder=f"Projects/{slug}/Contexts",
            frontmatter={"type": "project-context-index", "project_slug": slug},
            overwrite=False,
        )
        return {"slug": slug, "name": name}

    async def sync_skill_inventory(
        self,
        skill_inventory: list[dict[str, Any]],
        projects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        projects = projects or []
        await self._ensure_index("Skills", "Skills", "Canonical skill library for the vault.")
        created = 0
        sections: dict[str, list[str]] = {"technical": [], "soft": []}

        for skill in skill_inventory:
            name = _stringify(skill.get("name"))
            if not name:
                continue
            category = _stringify(skill.get("category")) or "technical"
            normalized_category = "soft" if category.lower() == "soft" else "technical"
            folder_name = "Soft" if normalized_category == "soft" else "Technical"
            slug = _slugify(name)
            project_links = []
            for project in projects:
                tech_stack = {
                    _slugify(_stringify(item))
                    for item in _as_list(project.get("tech_stack"))
                    if _stringify(item)
                }
                if slug in tech_stack:
                    project_links.append(self._project_link(_slugify(_stringify(project.get("name"))), _stringify(project.get("name"))))

            evidence = [
                f"- {item}"
                for item in (_stringify(entry) for entry in _as_list(skill.get("evidence")))
                if item
            ]
            content = f"""# {name}

## Category
{normalized_category}

## Level
{_stringify(skill.get("level")) or "unknown"}

## Years Experience
{_stringify(skill.get("years_experience")) or "unknown"}

## Evidence
{chr(10).join(evidence) if evidence else "- No evidence captured yet."}

## Related Projects
{chr(10).join(f"- {link}" for link in project_links) if project_links else "- No project links yet."}
"""
            await self.write_note(
                slug,
                content,
                folder=f"Skills/{folder_name}",
                frontmatter={
                    "type": "skill",
                    "skill_name": name,
                    "category": normalized_category,
                    "level": _stringify(skill.get("level")) or "unknown",
                    "created": _utc_now().isoformat(),
                },
                overwrite=True,
            )
            sections[normalized_category].append(
                f"- [[Skills/{folder_name}/{slug}|{name}]]"
            )
            created += 1

        index_content = (
            "# Skills\n\n"
            "## Technical\n"
            f"{chr(10).join(sections['technical']) if sections['technical'] else '- None yet.'}\n\n"
            "## Soft\n"
            f"{chr(10).join(sections['soft']) if sections['soft'] else '- None yet.'}\n"
        )
        await self.write_note(
            "Index",
            index_content,
            folder="Skills",
            frontmatter={"type": "skill-index", "created": _utc_now().isoformat()},
            overwrite=True,
        )
        return {"skill_count": created}

    async def bootstrap_second_brain(
        self,
        profile: dict[str, Any],
        skill_inventory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from app.integrations.obsidian_plugins import write_plugin_manifest, write_vault_templates

        projects = [
            item for item in _as_list(profile.get("projects")) if isinstance(item, dict)
        ]
        skills = skill_inventory or []
        goals = profile.get("goals") or {}
        current_status = profile.get("current_status") or {}

        # Generate plugin manifest and templates
        if self.vault_path:
            plugins_result = await write_plugin_manifest(self.vault_path)
            logger.info("obsidian_plugins_manifest_generated", plugins=plugins_result["plugins_written"])

            templates_result = await write_vault_templates(self.vault_path)
            logger.info("obsidian_vault_templates_written", template_count=templates_result["count"])

        await self.write_note(
            "Atlas",
            (
                "# Atlas\n\n"
                "- [[Dashboard]]\n"
                "- [[System/Identity]]\n"
                "- [[Projects/Index]]\n"
                "- [[Skills/Index]]\n"
                "- [[Operations/Index]]\n"
                "- [[CRM/Index]]\n"
                "- [[Knowledge/Index]]\n"
            ),
            frontmatter={"type": "atlas", "created": _utc_now().isoformat()},
            overwrite=True,
        )
        await self.write_note(
            "Dashboard",
            (
                "# Dashboard\n\n"
                f"## Role\n{_stringify(current_status.get('role')) or 'Unknown'}\n\n"
                "## Positioning\n"
                f"{_stringify(current_status.get('current_positioning')) or 'Unknown'}\n\n"
                "## North Star\n"
                f"{_stringify(goals.get('north_star')) or 'Not captured yet.'}\n\n"
                "## Active Projects\n"
                f"{chr(10).join(f'- {self._project_link(_slugify(_stringify(project.get('name'))), _stringify(project.get('name')))}' for project in projects) if projects else '- No projects defined.'}\n"
            ),
            frontmatter={"type": "dashboard", "created": _utc_now().isoformat()},
            overwrite=True,
        )
        await self.write_note(
            "Identity",
            (
                "# Identity\n\n"
                f"## Name\n{_stringify((profile.get('personal') or {}).get('name')) or 'Unknown'}\n\n"
                f"## Bio\n{_stringify((profile.get('personal') or {}).get('bio_short_en')) or 'No bio captured.'}\n"
            ),
            folder="System",
            frontmatter={"type": "identity", "created": _utc_now().isoformat()},
            overwrite=True,
        )
        await self.write_note(
            "Voice",
            (
                "# Voice\n\n"
                f"{_stringify((profile.get('voice_and_tone') or {}).get('english_style')) or 'No voice instructions captured.'}\n"
            ),
            folder="System",
            frontmatter={"type": "voice", "created": _utc_now().isoformat()},
            overwrite=True,
        )
        constraints = _as_list((profile.get("constraints") or {}).get("hard_limits"))
        await self.write_note(
            "Constraints",
            (
                "# Constraints\n\n"
                f"{chr(10).join(f'- {_stringify(item)}' for item in constraints if _stringify(item)) or '- No explicit constraints captured.'}\n"
            ),
            folder="System",
            frontmatter={"type": "constraints", "created": _utc_now().isoformat()},
            overwrite=True,
        )

        await self._ensure_index("Projects", "Projects", "All projects managed inside this shared Obsidian vault.")
        await self._ensure_index("Operations", "Operations", "Operational entities and execution logs.")
        await self._ensure_index("Operations/Opportunities", "Opportunities", "Tracked opportunities and scoring context.")
        await self._ensure_index("Operations/Submissions", "Submissions", "Tracked outbound submissions and applications.")
        await self._ensure_index("Operations/Tasks", "Tasks", "Operational task log.")
        await self._ensure_index("CRM", "CRM", "Relationship and contact management.")
        await self._ensure_index("CRM/Contacts", "Contacts", "People and relationship notes.")
        await self._ensure_index("Knowledge", "Knowledge", "Reusable lessons, playbooks, and structured knowledge.")
        await self._ensure_index("Knowledge/Playbooks", "Playbooks", "Winning patterns worth reusing.")
        await self._ensure_index("Knowledge/Failure Analyses", "Failure Analyses", "Post-mortems and lessons learned.")
        await self._ensure_index("Knowledge/Misc", "Misc Knowledge", "Other reusable knowledge captured by the system.")
        await self._ensure_index("Journal/Daily", "Daily Notes", "Daily execution log.")
        await self._ensure_index("Journal/Weekly", "Weekly Reviews", "Weekly review archive.")

        project_links: list[str] = []
        for project in projects:
            workspace = await self.ensure_project_workspace(project)
            project_links.append(
                f"- {self._project_link(workspace['slug'], workspace['name'])}"
            )

        await self.write_note(
            "Index",
            (
                "# Projects\n\n"
                f"{chr(10).join(project_links) if project_links else '- No projects captured.'}\n"
            ),
            folder="Projects",
            frontmatter={"type": "project-index", "created": _utc_now().isoformat()},
            overwrite=True,
        )

        skill_result = await self.sync_skill_inventory(skills, projects=projects)

        return {
            "root_folder": self.root_folder or "",
            "project_count": len(projects),
            "skill_count": skill_result["skill_count"],
        }

    async def capture_context_note(
        self,
        project_key: str,
        title: str,
        summary: str,
        details: str,
        tags: list[str] | None = None,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        project_name = project_key.strip() or "Untitled Project"
        project_slug = _slugify(project_name)
        await self.ensure_project_workspace({"name": project_name})

        timestamp = _utc_now().strftime("%Y%m%d-%H%M%S")
        note_slug = _slugify(title)
        filename = f"CTX-{timestamp}-{note_slug}"
        metadata_dump = yaml.safe_dump(
            _normalize_frontmatter(metadata or {}),
            sort_keys=False,
            allow_unicode=True,
        ).strip()
        content = f"""# {title}

## Summary
{summary}

## Details
{details}

## Source
{source_url or "N/A"}

## Metadata
```yaml
{metadata_dump or "{}"}
```
"""
        path = await self.write_note(
            filename,
            content,
            folder=f"Projects/{project_slug}/Contexts",
            frontmatter={
                "type": "project-context-note",
                "project_slug": project_slug,
                "title": title,
                "summary": summary,
                "tags": tags or [],
                "source_url": source_url,
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )

        link = f"[[Projects/{project_slug}/Contexts/{filename}|{title}]]"
        context_line = f"- {link}: {summary}"
        await self._ensure_unique_link(
            folder=f"Projects/{project_slug}",
            filename="Context",
            header=f"# Context - {project_name}",
            line=context_line,
            match_text=link,
        )
        await self._append_activity(project_slug, "Context captured", summary)
        return path

    async def create_daily_note(self, note_date: datetime | None = None) -> Path:
        if note_date is None:
            note_date = _utc_now()
        filename = note_date.strftime("%Y-%m-%d")
        return await self.write_note(
            filename,
            (
                f"# {note_date.strftime('%A, %B %d, %Y')}\n\n"
                "## Focus\n\n"
                "## Wins\n\n"
                "## Open Loops\n\n"
                "## Decisions\n\n"
                "## Notes\n"
            ),
            folder="Journal/Daily",
            frontmatter={
                "type": "daily-note",
                "date": note_date.strftime("%Y-%m-%d"),
                "created": _utc_now().isoformat(),
            },
            overwrite=False,
        )

    async def create_weekly_review(
        self,
        week_start: datetime,
        review_data: dict[str, Any] | None = None,
    ) -> Path:
        review_data = review_data or {}
        filename = f"Week-{week_start.strftime('%Y-W%W')}"
        return await self.write_note(
            filename,
            (
                f"# Weekly Review - {week_start.strftime('%B %d, %Y')}\n\n"
                "## Metrics\n"
                f"- Opportunities: {_stringify(review_data.get('opportunities')) or '0'}\n"
                f"- Submissions: {_stringify(review_data.get('submissions')) or '0'}\n"
                f"- Wins: {_stringify(review_data.get('wins')) or '0'}\n"
                f"- Losses: {_stringify(review_data.get('losses')) or '0'}\n\n"
                "## Highlights\n"
                f"{_stringify(review_data.get('highlights')) or 'Capture the best outcomes here.'}\n\n"
                "## Learnings\n"
                f"{_stringify(review_data.get('learnings')) or 'Capture patterns and corrections here.'}\n"
            ),
            folder="Journal/Weekly",
            frontmatter={
                "type": "weekly-review",
                "week": week_start.strftime("%Y-W%W"),
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )

    async def log_opportunity(self, opportunity: dict[str, Any]) -> Path:
        project_slug = _stringify(
            opportunity.get("project_slug")
            or (opportunity.get("raw_data") or {}).get("project_slug")
        )
        title = _stringify(opportunity.get("title")) or "Untitled opportunity"
        opportunity_id = _stringify(opportunity.get("id")) or "unknown"
        filename = f"OPP-{opportunity_id}"
        content = f"""# {title}

## Source
- Platform: {_stringify(opportunity.get('source_platform') or opportunity.get('source')) or 'N/A'}
- URL: {_stringify(opportunity.get('source_url') or opportunity.get('url')) or 'N/A'}

## Status
- Status: {_stringify(opportunity.get('status')) or 'new'}
- Score: {_stringify(opportunity.get('score')) or 'N/A'}
- Action Priority: {_stringify(opportunity.get('action_priority')) or 'N/A'}
- Deadline: {_stringify(opportunity.get('deadline')) or 'N/A'}

## Description
{_stringify(opportunity.get('description')) or 'No description'}

## Analysis
{_stringify(opportunity.get('scoring_rationale') or opportunity.get('analysis')) or 'Pending analysis'}
"""
        path = await self.write_note(
            filename,
            content,
            folder="Operations/Opportunities",
            frontmatter={
                "type": "opportunity",
                "status": _stringify(opportunity.get("status")) or "new",
                "score": opportunity.get("score"),
                "action_priority": _stringify(opportunity.get("action_priority")) or "",
                "project_slug": project_slug or None,
                "tags": _as_list(opportunity.get("tags")),
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )
        link = f"[[Operations/Opportunities/{filename}|{title}]]"
        await self._ensure_unique_link(
            folder="Operations/Opportunities",
            filename="Index",
            header="# Opportunities",
            line=f"- {link}",
            match_text=link,
        )
        if project_slug:
            await self.ensure_project_workspace({"name": project_slug})
            await self._append_activity(project_slug, "Opportunity synced", title)
        return path

    async def log_submission(self, submission: dict[str, Any]) -> Path:
        title = _stringify(submission.get("title")) or "Untitled submission"
        submission_id = _stringify(submission.get("id")) or "unknown"
        filename = f"SUB-{submission_id}"
        content = f"""# {title}

## Submission Details
- Status: {_stringify(submission.get('status')) or 'sent'}
- Sent At: {_stringify(submission.get('sent_at')) or 'N/A'}
- Opportunity: {_stringify(submission.get('opportunity_id')) or 'N/A'}

## Content
{_stringify(submission.get('proposal_text') or submission.get('content')) or 'No content'}

## Outcome Notes
{_stringify(submission.get('outcome') or submission.get('outcome_notes')) or 'Pending'}
"""
        path = await self.write_note(
            filename,
            content,
            folder="Operations/Submissions",
            frontmatter={
                "type": "submission",
                "status": _stringify(submission.get("status")) or "sent",
                "opportunity_id": _stringify(submission.get("opportunity_id")) or None,
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )
        link = f"[[Operations/Submissions/{filename}|{title}]]"
        await self._ensure_unique_link(
            folder="Operations/Submissions",
            filename="Index",
            header="# Submissions",
            line=f"- {link}",
            match_text=link,
        )
        return path

    async def create_contact_note(self, contact: dict[str, Any]) -> Path:
        name = _stringify(contact.get("name")) or "Unknown contact"
        filename = _slugify(name)
        content = f"""# {name}

## Contact Info
- Email: {_stringify(contact.get('email')) or 'N/A'}
- Company: {_stringify(contact.get('company')) or 'N/A'}
- Role: {_stringify(contact.get('role')) or 'N/A'}
- LinkedIn: {_stringify(contact.get('linkedin_url')) or 'N/A'}

## Relationship
- Strength: {_stringify(contact.get('relationship_strength')) or 'N/A'}
- Last Contacted: {_stringify(contact.get('last_contacted_at') or contact.get('last_interaction_date')) or 'N/A'}

## Notes
{_stringify(contact.get('notes') or contact.get('conversation_summary')) or 'No notes yet.'}
"""
        path = await self.write_note(
            filename,
            content,
            folder="CRM/Contacts",
            frontmatter={
                "type": "contact",
                "email": _stringify(contact.get("email")) or None,
                "company": _stringify(contact.get("company")) or None,
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )
        link = f"[[CRM/Contacts/{filename}|{name}]]"
        await self._ensure_unique_link(
            folder="CRM/Contacts",
            filename="Index",
            header="# Contacts",
            line=f"- {link}",
            match_text=link,
        )
        return path

    async def log_task(self, task: dict[str, Any]) -> Path:
        task_id = _stringify(task.get("id")) or "unknown"
        title = _stringify(task.get("title")) or "Untitled task"
        filename = f"TASK-{task_id}"
        content = f"""# {title}

## Status
- Status: {_stringify(task.get('status')) or 'pending'}
- Priority: {_stringify(task.get('priority')) or 'N/A'}
- Due Date: {_stringify(task.get('due_date')) or 'N/A'}
- Assigned To: {_stringify(task.get('assigned_to')) or 'user'}

## Description
{_stringify(task.get('description')) or 'No description'}

## Related Entity
- Type: {_stringify(task.get('related_entity_type')) or 'N/A'}
- ID: {_stringify(task.get('related_entity_id')) or 'N/A'}
"""
        path = await self.write_note(
            filename,
            content,
            folder="Operations/Tasks",
            frontmatter={
                "type": "task",
                "status": _stringify(task.get("status")) or "pending",
                "priority": task.get("priority"),
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )
        link = f"[[Operations/Tasks/{filename}|{title}]]"
        await self._ensure_unique_link(
            folder="Operations/Tasks",
            filename="Index",
            header="# Tasks",
            line=f"- {link}",
            match_text=link,
        )
        return path

    async def log_knowledge_item(self, item: dict[str, Any]) -> Path:
        category = _stringify(item.get("category")) or "misc"
        folder_mapping = {
            "playbook": "Knowledge/Playbooks",
            "failure_analysis": "Knowledge/Failure Analyses",
        }
        folder = folder_mapping.get(category, "Knowledge/Misc")
        title = _stringify(item.get("title")) or "Untitled knowledge item"
        item_id = _stringify(item.get("id")) or "unknown"
        filename = f"{_slugify(category)}-{item_id}"
        content = f"""# {title}

## Category
{category}

## Content
{_stringify(item.get('content')) or 'No content'}

## Tags
{", ".join(_stringify(tag) for tag in _as_list(item.get('tags')) if _stringify(tag)) or 'N/A'}
"""
        path = await self.write_note(
            filename,
            content,
            folder=folder,
            frontmatter={
                "type": "knowledge-item",
                "category": category,
                "tags": _as_list(item.get("tags")),
                "created": _utc_now().isoformat(),
            },
            overwrite=True,
        )
        link = f"[[{folder}/{filename}|{title}]]"
        await self._ensure_unique_link(
            folder=folder,
            filename="Index",
            header=f"# {_folder_title(folder)}",
            line=f"- {link}",
            match_text=link,
        )
        return path


def build_obsidian_connector() -> ObsidianConnector | None:
    vault_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)
    api_url = getattr(settings, "OBSIDIAN_API_URL", None)
    api_key = getattr(settings, "OBSIDIAN_API_KEY", None)
    root_folder = getattr(settings, "OBSIDIAN_ROOT_FOLDER", "Second Brain")

    if not vault_path and not api_url:
        logger.warning("obsidian_not_configured")
        return None

    return ObsidianConnector(
        vault_path=vault_path,
        api_url=api_url,
        api_key=api_key,
        root_folder=root_folder,
    )


obsidian_connector: ObsidianConnector | None = None


async def get_obsidian() -> ObsidianConnector:
    global obsidian_connector
    if obsidian_connector is None:
        obsidian_connector = build_obsidian_connector()
        if obsidian_connector is None:
            raise ValueError("Obsidian not configured")
    return obsidian_connector
