import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    passed: bool
    details: str


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""

def _load_dotenv_into_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in _read_text(env_path).splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ and os.environ[key]:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _json_get(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except Exception:
        return None


def _check_auth_smoke() -> Check:
    base = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    email = os.environ.get("GOOGLE_WORKSPACE_EMAIL") or os.environ.get("ADMIN_DEFAULT_EMAIL") or "admin@local"
    password = os.environ.get("ADMIN_DEFAULT_PASSWORD") or ""
    if not password:
        return Check(
            "Auth smoke (/login + /me)",
            False,
            "ADMIN_DEFAULT_PASSWORD is not set; cannot verify login automatically.",
        )
    try:
        with httpx.Client(base_url=base, timeout=10.0, follow_redirects=True) as client:
            resp = client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                return Check("Auth smoke (/login + /me)", False, f"login status={resp.status_code} body={resp.text[:200]}")
            me = client.get("/api/v1/auth/me")
            if me.status_code != 200:
                return Check("Auth smoke (/login + /me)", False, f"me status={me.status_code} body={me.text[:200]}")
            suffix = " (password is placeholder)" if password == "changeme" else ""
            return Check("Auth smoke (/login + /me)", True, f"login=200, me=200 (cookies/session OK){suffix}")
    except Exception as exc:
        return Check("Auth smoke (/login + /me)", False, f"error={exc} (backend not reachable?)")


def _check_auth_bootstrap_seed() -> list[Check]:
    main_py = ROOT / "backend" / "app" / "main.py"
    bootstrap_py = ROOT / "backend" / "app" / "core" / "bootstrap.py"
    main_txt = _read_text(main_py)
    boot_txt = _read_text(bootstrap_py)
    has_import = "seed_admin_user" in main_txt
    has_impl = "async def seed_admin_user" in boot_txt
    return [
        Check("Backend: seed_admin_user referenced", has_import, str(main_py)),
        Check("Backend: seed_admin_user implemented", has_impl, str(bootstrap_py)),
    ]


def _check_react_router_flags() -> Check:
    app_tsx = ROOT / "frontend" / "src" / "App.tsx"
    content = _read_text(app_tsx)
    ok = "v7_startTransition" in content and "v7_relativeSplatPath" in content
    return Check("React Router future flags", ok, str(app_tsx))


def _check_ide_settings() -> list[Check]:
    appdata = Path(os.environ.get("APPDATA", ""))
    targets = [
        appdata / "Code" / "User" / "settings.json",
        appdata / "Trae" / "User" / "settings.json",
        appdata / "Cursor" / "User" / "settings.json",
        appdata / "Windsurf" / "User" / "settings.json",
        appdata / "Antigravity" / "User" / "settings.json",
        appdata / "Kiro" / "User" / "settings.json",
    ]
    out: list[Check] = []
    for path in targets:
        if not path.exists():
            out.append(Check(f"IDE settings: {path.parent.parent.name}", False, "settings file not found"))
            continue
        text = _read_text(path)
        has_location = "claudeCode.preferredLocation" in text
        has_model = "claudeCode.selectedModel" in text
        has_import = "AI.rules.importClaudeMd" in text
        ok = has_location and has_model and has_import
        out.append(
            Check(
                f"IDE settings: {path.parent.parent.name}",
                ok,
                f"path={path} preferredLocation={has_location} selectedModel={has_model} importClaudeMd={has_import}",
            )
        )
    return out


def _check_brain_markers() -> list[Check]:
    home = Path(os.environ.get("USERPROFILE", ""))
    targets = [
        home / ".claude" / "CLAUDE.md",
        home / ".codex" / "AGENTS.md",
        home / ".gemini" / "GEMINI.md",
    ]
    out: list[Check] = []
    for path in targets:
        text = _read_text(path)
        ok = "<!--BRAIN_SNAPSHOT_START-->" in text and "<!--BRAIN_SNAPSHOT_END-->" in text
        out.append(Check(f"Brain markers: {path.name}", ok, str(path)))
    return out


def _check_gemini_hook() -> Check:
    home = Path(os.environ.get("USERPROFILE", ""))
    settings_path = home / ".gemini" / "settings.json"
    data = _json_get(settings_path) or {}
    hooks = (((data.get("hooks") or {}).get("SessionStart")) or [])
    blob = json.dumps(hooks)
    ok = "sync_obsidian_brain.ps1" in blob
    return Check("Gemini SessionStart hook", ok, str(settings_path))


def _run_cmd(name: str, cwd: Path, command: list[str], timeout_s: int = 600) -> Check:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )
        ok = proc.returncode == 0
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-6:]
        detail = " | ".join(tail)[:220] if tail else f"exit={proc.returncode}"
        return Check(name, ok, detail)
    except Exception as exc:
        return Check(name, False, f"error={exc}")


def main() -> int:
    _load_dotenv_into_env()
    checks: list[Check] = []
    checks.append(_check_auth_smoke())
    checks.extend(_check_auth_bootstrap_seed())
    checks.append(_check_react_router_flags())
    checks.extend(_check_ide_settings())
    checks.extend(_check_brain_markers())
    checks.append(_check_gemini_hook())
    checks.append(_run_cmd("Backend tests (pytest)", ROOT / "backend", ["python", "-m", "pytest", "tests", "-q"], timeout_s=1200))
    checks.append(
        _run_cmd(
            "Frontend tests (npm test)",
            ROOT / "frontend",
            ["powershell", "-NoProfile", "-Command", "npm test"],
            timeout_s=1200,
        )
    )

    passed = sum(1 for c in checks if c.passed)
    total = len(checks)

    report = ROOT / "GUARANTEE_REPORT.md"
    lines = []
    lines.append(f"# Project Guarantee Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Passed: {passed}/{total}")
    lines.append("")
    lines.append("| Check | Status | Details |")
    lines.append("|---|---:|---|")
    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        details = c.details.replace("\n", " ").strip()
        details = re.sub(r"\s+", " ", details)[:220]
        lines.append(f"| {c.name} | {status} | {details} |")
    lines.append("")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(report))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
