#!/usr/bin/env python3
"""Verify the file-based Universal Skills Hub."""

from __future__ import annotations

import json
from pathlib import Path


HOME = Path.home()
WORKSPACE = Path("c:/brav os")
HUB = HOME / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "skills-universal"
REGISTRY = HUB / "skills-registry.json"
COMPACT_REGISTRY = HUB / "skills-registry-compact.json"
ROUTER = HUB / "skills-router.md"


def link_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_symlink():
        return f"symlink -> {path.resolve()}"
    if path.is_dir():
        return "directory"
    return "file"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    checks.append(("hub exists", HUB.exists(), str(HUB)))
    checks.append(("full registry exists", REGISTRY.exists(), str(REGISTRY)))
    checks.append(("compact registry exists", COMPACT_REGISTRY.exists(), str(COMPACT_REGISTRY)))
    checks.append(("router exists", ROUTER.exists(), str(ROUTER)))
    checks.append(("workspace skills link", (WORKSPACE / "skills").exists(), link_status(WORKSPACE / "skills")))
    checks.append(
        ("VS Code skills link", (WORKSPACE / ".vscode" / "skills").exists(), link_status(WORKSPACE / ".vscode" / "skills"))
    )
    checks.append(
        (
            "project Claude universal link",
            (WORKSPACE / ".claude" / "skills-universal").exists(),
            link_status(WORKSPACE / ".claude" / "skills-universal"),
        )
    )
    checks.append(("home Claude skills-all", (HOME / ".claude" / "skills-all").exists(), link_status(HOME / ".claude" / "skills-all")))
    checks.append(
        (
            "Codex bridge skill",
            (HOME / ".codex" / "skills" / "gracia-universal-skills" / "SKILL.md").exists(),
            str(HOME / ".codex" / "skills" / "gracia-universal-skills" / "SKILL.md"),
        )
    )

    total_skills = 0
    if REGISTRY.exists():
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        total_skills = int(data.get("total_skills", 0))
        checks.append(("registry has skills", total_skills > 0, f"{total_skills} indexed"))

    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"{marker}: {name} - {detail}")

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"\nFailed checks: {', '.join(failed)}")
        return 1

    print(f"\nUniversal Skills Hub ready: {total_skills} skills indexed.")
    print("Policy: read skills-router.md, search compact registry, load only selected SKILL.md files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
