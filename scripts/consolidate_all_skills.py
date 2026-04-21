#!/usr/bin/env python3
"""
Build a no-daemon universal skills hub in Obsidian.

The hub is a file-based source of truth. Agents should read the compact router
and registry first, then load only the SKILL.md files that are relevant to the
current task.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


HOME = Path.home()
WORKSPACE = Path("c:/brav os")
OBSIDIAN_BRAIN = HOME / "Documents" / "ObsidianVault" / "Second Brain" / "brain"
UNIVERSAL_HUB = OBSIDIAN_BRAIN / "skills-universal"
REGISTRY_FILE = UNIVERSAL_HUB / "skills-registry.json"
COMPACT_REGISTRY_FILE = UNIVERSAL_HUB / "skills-registry-compact.json"
ROUTER_FILE = UNIVERSAL_HUB / "skills-router.md"
README_FILE = UNIVERSAL_HUB / "README.md"
CLAUDE_AI_FILE = UNIVERSAL_HUB / "claude-ai-custom-instructions.md"


IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "dist",
    "build",
}


@dataclass(frozen=True)
class SourceSpec:
    key: str
    root: Path
    family: str
    priority: int


@dataclass
class SkillSource:
    base_id: str
    display_name: str
    source_file: Path
    source_dir: Path
    family: str
    priority: int
    description: str
    tokens_estimate: int
    content_hash: str
    aliases: list[str]


SOURCE_SPECS = [
    SourceSpec("codex-system", HOME / ".codex" / "skills" / ".system", "codex-system", 10),
    SourceSpec("codex-user", HOME / ".codex" / "skills", "codex", 20),
    SourceSpec("codex-plugin", HOME / ".codex" / "plugins" / "cache", "codex-plugin", 30),
    SourceSpec("claude-home", HOME / ".claude" / "skills", "claude", 40),
    SourceSpec("agents", HOME / ".agents" / "skills", "automation", 50),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "skill"


def should_skip_dir(path: Path) -> bool:
    return path.name in IGNORE_DIRS


def walk_skill_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return

    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        if should_skip_dir(current_path):
            dirs[:] = []
            continue

        if "SKILL.md" in files:
            yield current_path / "SKILL.md"


def parse_frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip().strip("'\"")
        if value:
            metadata[key.strip().lower()] = value
    return metadata


def first_heading(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def first_sentence(content: str) -> str:
    body = re.sub(r"---.*?---", "", content, count=1, flags=re.DOTALL).strip()
    body = re.sub(r"#+\s*", "", body)
    body = re.sub(r"\s+", " ", body)
    if not body:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", body)[0]
    return sentence[:220]


def infer_plugin_name(path: Path) -> str | None:
    parts = list(path.parts)
    try:
        idx = parts.index("openai-curated")
    except ValueError:
        return None

    if len(parts) > idx + 1:
        return parts[idx + 1]
    return None


def infer_display_name(spec: SourceSpec, skill_file: Path) -> str:
    name = skill_file.parent.name

    if spec.key == "codex-system":
        return f"codex-system:{name}"

    if spec.key == "codex-plugin":
        plugin = infer_plugin_name(skill_file)
        return f"{plugin}:{name}" if plugin else f"plugin:{name}"

    if ".gemini" in skill_file.parts:
        return f"gemini:{name}"

    return name


def infer_category(display_name: str, family: str, description: str) -> str:
    text = f"{display_name} {description}".lower()
    if family == "automation" or display_name.endswith("-automation"):
        return "automation"
    if family == "codex-plugin":
        return "plugin"
    if "security" in text or "threat" in text:
        return "security"
    if "deploy" in text or "vercel" in text or "cloudflare" in text or "netlify" in text:
        return "deployment"
    if "test" in text or "tdd" in text or "playwright" in text:
        return "testing"
    if "figma" in text or "design" in text or "ui" in text:
        return "design"
    if "pdf" in text or "doc" in text or "spreadsheet" in text or "transcribe" in text:
        return "documents"
    if "openai" in text or "chatgpt" in text or "llm" in text:
        return "ai"
    return family


def read_skill_source(spec: SourceSpec, skill_file: Path) -> SkillSource | None:
    try:
        content = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = skill_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    metadata = parse_frontmatter(content)
    display_name = metadata.get("name") or metadata.get("skill-name") or infer_display_name(spec, skill_file)
    description = metadata.get("description") or first_sentence(content) or first_heading(content)
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    base_id = slugify(display_name)
    if spec.key == "codex-plugin" and ":" in display_name:
        base_id = slugify(display_name)
    elif spec.key == "codex-system":
        base_id = slugify(display_name)
    elif spec.key == "agents":
        base_id = slugify(display_name)

    aliases = sorted({display_name, skill_file.parent.name, base_id})

    return SkillSource(
        base_id=base_id,
        display_name=display_name,
        source_file=skill_file,
        source_dir=skill_file.parent,
        family=spec.family,
        priority=spec.priority,
        description=description,
        tokens_estimate=max(1, len(content) // 4),
        content_hash=digest,
        aliases=aliases,
    )


def discover_skills() -> list[SkillSource]:
    skills: list[SkillSource] = []
    seen_paths: set[Path] = set()

    for spec in SOURCE_SPECS:
        if not spec.root.exists():
            continue

        for skill_file in walk_skill_files(spec.root):
            resolved = skill_file.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            # The codex-user root includes .system, which is scanned separately
            # with higher priority.
            if spec.key == "codex-user" and ".system" in skill_file.parts:
                continue

            source = read_skill_source(spec, skill_file)
            if source:
                skills.append(source)

    return sorted(skills, key=lambda item: (item.priority, item.base_id, str(item.source_file).lower()))


def assign_ids(skills: list[SkillSource]) -> dict[str, SkillSource]:
    assigned: dict[str, SkillSource] = {}
    used_hash_by_id: dict[str, str] = {}

    for skill in skills:
        skill_id = skill.base_id

        if skill_id in assigned:
            existing = assigned[skill_id]
            if existing.content_hash == skill.content_hash:
                existing.aliases = sorted(set(existing.aliases + skill.aliases))
                continue

            family_id = slugify(f"{skill.family}-{skill.base_id}")
            skill_id = family_id

            if skill_id in assigned and assigned[skill_id].content_hash != skill.content_hash:
                skill_id = f"{family_id}-{skill.content_hash[:8]}"

        if skill_id in used_hash_by_id and used_hash_by_id[skill_id] == skill.content_hash:
            continue

        assigned[skill_id] = skill
        used_hash_by_id[skill_id] = skill.content_hash

    return assigned


def copy_skill_dir(source: SkillSource, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)

    def ignore(_: str, names: list[str]) -> set[str]:
        return {name for name in names if name in IGNORE_DIRS}

    shutil.copytree(source.source_dir, target_dir, ignore=ignore, symlinks=False)


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def build_registry(assigned: dict[str, SkillSource]) -> tuple[dict[str, object], dict[str, object]]:
    generated_at = utc_now()
    records = []
    compact_records = []
    by_category: dict[str, int] = {}
    by_family: dict[str, int] = {}

    for skill_id, source in sorted(assigned.items()):
        category = infer_category(source.display_name, source.family, source.description)
        relative_skill_file = f"{skill_id}/SKILL.md"
        by_category[category] = by_category.get(category, 0) + 1
        by_family[source.family] = by_family.get(source.family, 0) + 1

        record = {
            "id": skill_id,
            "name": source.display_name,
            "aliases": source.aliases,
            "description": source.description,
            "category": category,
            "family": source.family,
            "hub_path": str((UNIVERSAL_HUB / relative_skill_file).resolve()),
            "relative_path": relative_skill_file,
            "source_path": str(source.source_file),
            "tokens_estimate": source.tokens_estimate,
            "content_sha256": source.content_hash,
        }
        records.append(record)
        compact_records.append(
            {
                "id": skill_id,
                "name": source.display_name,
                "description": source.description,
                "category": category,
                "family": source.family,
                "path": relative_skill_file,
                "tokens": source.tokens_estimate,
            }
        )

    registry = {
        "version": "3.0.0",
        "generated_at": generated_at,
        "hub": str(UNIVERSAL_HUB),
        "router": str(ROUTER_FILE),
        "total_skills": len(records),
        "by_category": dict(sorted(by_category.items())),
        "by_family": dict(sorted(by_family.items())),
        "load_policy": {
            "default": "Read skills-router.md first, then load only selected SKILL.md files.",
            "max_skill_files_per_task": 3,
            "prefer_compact_registry": True,
            "no_background_process_required": True,
        },
        "skills": records,
    }

    compact = {
        "version": registry["version"],
        "generated_at": generated_at,
        "hub": str(UNIVERSAL_HUB),
        "total_skills": len(compact_records),
        "by_category": registry["by_category"],
        "by_family": registry["by_family"],
        "skills": compact_records,
    }
    return registry, compact


def write_router(registry: dict[str, object], compact: dict[str, object]) -> None:
    by_category = registry["by_category"]
    by_family = registry["by_family"]

    lines = [
        "# Universal Skills Router",
        "",
        f"Generated: {registry['generated_at']}",
        f"Hub: `{UNIVERSAL_HUB}`",
        f"Total indexed skills: {registry['total_skills']}",
        "",
        "## Operating Rule",
        "",
        "Do not load every skill into context. Use this order:",
        "",
        "1. Read `skills-registry-compact.json` when you need to choose a skill.",
        "2. Pick the smallest useful set of skills, usually 1 skill and never more than 3 unless the user asks.",
        "3. Load only the selected `<skill-id>/SKILL.md` files.",
        "4. If a named skill is missing, search aliases in `skills-registry.json`.",
        "5. Prefer project instructions and live code over skill text when they conflict.",
        "",
        "## Source Families",
        "",
    ]

    for family, count in sorted(by_family.items()):
        lines.append(f"- `{family}`: {count}")

    lines.extend(["", "## Categories", ""])
    for category, count in sorted(by_category.items()):
        lines.append(f"- `{category}`: {count}")

    lines.extend(
        [
            "",
            "## Routing Hints",
            "",
            "- Coding in this repo: first obey `AGENTS.md`, `CLAUDE.md`, live code, and tests.",
            "- OpenAI, ChatGPT Apps, Sora, image generation, speech: search `openai`, `chatgpt`, `sora`, `imagegen`, or `speech`.",
            "- Vercel, Next.js, deployment: search `vercel`, `nextjs`, `deploy`, or `cloudflare`.",
            "- Figma or design-to-code: search `figma` or `design`.",
            "- Security review or threat modeling: search `security` or `threat`.",
            "- Browser/UI verification: search `playwright`, `browser`, or `verification`.",
            "- SaaS/API automation: search `<service-name>-automation`.",
            "- Documents and files: search `pdf`, `doc`, `spreadsheet`, `transcribe`, or `jupyter`.",
            "",
            "## Token Budget",
            "",
            "- Router only: about 300-600 tokens.",
            "- Compact registry lookup: load snippets or search within JSON; do not paste the whole file into the answer.",
            "- Selected skills: load only the full `SKILL.md` files needed for the task.",
            "",
            "## Files",
            "",
            f"- Full registry: `{REGISTRY_FILE}`",
            f"- Compact registry: `{COMPACT_REGISTRY_FILE}`",
            f"- Claude.ai instructions: `{CLAUDE_AI_FILE}`",
        ]
    )

    ROUTER_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(registry: dict[str, object]) -> None:
    content = f"""# Universal AI Skills Hub

This folder is the Obsidian source of truth for local AI skills.

Generated: {registry['generated_at']}
Total indexed skills: {registry['total_skills']}

## How agents should use this hub

1. Read `skills-router.md`.
2. Search `skills-registry-compact.json` for the task.
3. Load only the relevant `<skill-id>/SKILL.md` files.
4. Keep loaded skills to 1-3 files per task.

This is intentionally file-based. No API server, daemon, watcher, or background
script is required after the files and junctions exist.

## Important limit

Local agents can read this hub when their environment gives them filesystem
access. Web-only tools such as Claude.ai or Gemini cannot read local Obsidian
files by themselves; use `claude-ai-custom-instructions.md` or paste the needed
skill text when the web app has no local-file connector.
"""
    README_FILE.write_text(content, encoding="utf-8")


def write_claude_ai_instructions(registry: dict[str, object]) -> None:
    content = f"""# Claude.ai Custom Instructions: Universal Skills Hub

I maintain a local Obsidian skills hub:

`{UNIVERSAL_HUB}`

Use this policy when I ask for a skill or when a task clearly matches a skill:

1. Do not assume all skill text is already in context.
2. Ask me to provide the relevant skill file if you cannot access local files.
3. If local file access is available, read `skills-router.md` first.
4. Search `skills-registry-compact.json` and load only 1-3 relevant `SKILL.md` files.
5. Prefer the user's current repo instructions and live code over generic skill guidance.

Current indexed skills: {registry['total_skills']}.
"""
    CLAUDE_AI_FILE.write_text(content, encoding="utf-8")


def ensure_junction_or_symlink(source: Path, target: Path) -> str:
    target_parent = target.parent
    target_parent.mkdir(parents=True, exist_ok=True)

    if target.exists() or target.is_symlink():
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            # Leave real directories alone to avoid destroying user files.
            return "kept-existing-directory"
        else:
            return "kept-existing-file"

    try:
        os.symlink(str(source), str(target), target_is_directory=True)
        return "symlink"
    except OSError:
        # Junctions are more reliable on Windows without admin/developer mode.
        import subprocess

        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return "junction"
        return f"failed: {completed.stderr.strip() or completed.stdout.strip()}"


def write_codex_bridge_skill() -> None:
    bridge_dir = HOME / ".codex" / "skills" / "gracia-universal-skills"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    bridge_file = bridge_dir / "SKILL.md"
    content = f"""---
name: gracia-universal-skills
description: Use when the user asks to use, route, share, or look up AI skills across Claude, Codex, Gemini, Copilot, automation tools, or the Obsidian universal skills hub. Keeps token use low by loading only selected skill files.
---

# Gracia Universal Skills

Use the Obsidian hub as the cross-AI skill source of truth.

Hub: `{UNIVERSAL_HUB}`
Router: `{ROUTER_FILE}`
Compact registry: `{COMPACT_REGISTRY_FILE}`

Workflow:

1. Read `skills-router.md` first.
2. Search `skills-registry-compact.json` for candidate skills.
3. Load only the selected `<skill-id>/SKILL.md` files.
4. Use at most 3 skill files unless the user explicitly asks for more.
5. Never paste the whole registry or hub into the conversation.
"""
    bridge_file.write_text(content, encoding="utf-8")


def create_bridges() -> dict[str, str]:
    bridges = {
        "workspace_skills": ensure_junction_or_symlink(UNIVERSAL_HUB, WORKSPACE / "skills"),
        "vscode_skills": ensure_junction_or_symlink(UNIVERSAL_HUB, WORKSPACE / ".vscode" / "skills"),
        "project_claude_skills_universal": ensure_junction_or_symlink(
            UNIVERSAL_HUB, WORKSPACE / ".claude" / "skills-universal"
        ),
        "home_claude_skills_all": ensure_junction_or_symlink(UNIVERSAL_HUB, HOME / ".claude" / "skills-all"),
    }

    write_codex_bridge_skill()
    bridges["codex_bridge_skill"] = str(HOME / ".codex" / "skills" / "gracia-universal-skills" / "SKILL.md")
    return bridges


def main() -> int:
    UNIVERSAL_HUB.mkdir(parents=True, exist_ok=True)

    discovered = discover_skills()
    assigned = assign_ids(discovered)

    if not assigned:
        print("No skills found. Check source directories.")
        return 1

    for skill_id, source in assigned.items():
        copy_skill_dir(source, UNIVERSAL_HUB / skill_id)

    registry, compact = build_registry(assigned)
    write_json(REGISTRY_FILE, registry)
    write_json(COMPACT_REGISTRY_FILE, compact)
    write_router(registry, compact)
    write_readme(registry)
    write_claude_ai_instructions(registry)
    bridges = create_bridges()

    print("Universal skills hub generated")
    print(f"Hub: {UNIVERSAL_HUB}")
    print(f"Skills indexed: {registry['total_skills']}")
    print(f"Registry: {REGISTRY_FILE}")
    print(f"Compact registry: {COMPACT_REGISTRY_FILE}")
    print(f"Router: {ROUTER_FILE}")
    print("Bridges:")
    for name, status in bridges.items():
        print(f"  {name}: {status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
