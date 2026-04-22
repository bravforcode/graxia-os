#!/usr/bin/env python3
"""Local production env audit before Docker-based preflight."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402


@dataclass
class AuditResult:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(1 for _name, ok, _message in self.checks if not ok)

    def add(self, name: str, ok: bool, message: str) -> None:
        self.checks.append((name, ok, message))

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw_line:
            raise RuntimeError(f"{path}:{lineno} is not a valid KEY=VALUE line")
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _check_compose_frontend_bridge(compose_file: Path, result: AuditResult) -> None:
    compose_text = compose_file.read_text(encoding="utf-8")
    expected_args = {
        "VITE_API_BASE_URL": "frontend build must inject VITE_API_BASE_URL",
        "VITE_AGENT_STREAM_URL": "frontend build must inject VITE_AGENT_STREAM_URL",
        "VITE_SUPABASE_URL": "frontend build must inject VITE_SUPABASE_URL",
        "VITE_SUPABASE_ANON_KEY": "frontend build must inject VITE_SUPABASE_ANON_KEY",
    }
    for env_name, message in expected_args.items():
        result.add(
            f"compose bridge {env_name}",
            f"{env_name}:" in compose_text,
            message,
        )


def _check_required_secret_files(repo_root: Path, result: AuditResult) -> None:
    required_secret_files = {
        repo_root / "secrets" / "backup_private_key.txt": "backup private key mount source must exist",
        repo_root / "secrets" / "alertmanager_webhook_token.txt": "alertmanager webhook token file must exist",
    }
    for path, message in required_secret_files.items():
        ok = path.exists() and path.is_file()
        result.add(
            f"secret file {path.name}",
            ok,
            message if ok else f"{message}: missing {path.relative_to(repo_root)}",
        )


def _warn_if_local_artifacts_exist(repo_root: Path, result: AuditResult) -> None:
    suspicious_paths = {
        repo_root / ".env.bak_gemini",
        repo_root / "backend" / "staging-token.json",
        repo_root / "backend" / ".coverage",
        repo_root / "dump.rdb",
    }
    suspicious_paths.update((repo_root / "backend").glob("celerybeat-schedule*"))
    suspicious_paths.update((repo_root / "backend").glob("C*"))
    for path in sorted(suspicious_paths):
        if path.exists():
            relative = path.relative_to(repo_root)
            display = str(relative).encode("ascii", "backslashreplace").decode("ascii")
            result.warn(f"local artifact or secret-like file present: {display}")


def audit_production_env(
    env_file: Path,
    compose_file: Path,
    frontend_env_file: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> AuditResult:
    result = AuditResult()

    if not env_file.exists():
        result.add("env file", False, f"{env_file} does not exist")
        return result
    if not compose_file.exists():
        result.add("compose file", False, f"{compose_file} does not exist")
        return result

    env_values = parse_env_file(env_file)
    settings = Settings(**env_values)

    production_errors = settings.get_production_configuration_errors()
    if production_errors:
        for error in production_errors:
            result.add("production configuration", False, error)
    else:
        result.add("production configuration", True, "strict settings accepted")

    _check_compose_frontend_bridge(compose_file, result)
    _check_required_secret_files(repo_root, result)

    if frontend_env_file and frontend_env_file.exists():
        frontend_env = parse_env_file(frontend_env_file)
        placeholder_keys = [
            key
            for key in (
                "VITE_API_BASE_URL",
                "VITE_AGENT_STREAM_URL",
                "VITE_SUPABASE_URL",
                "VITE_SUPABASE_ANON_KEY",
            )
            if settings._looks_placeholder(frontend_env.get(key, ""))
        ]
        if placeholder_keys:
            result.warn(
                "frontend/.env.production still contains placeholder values for "
                + ", ".join(placeholder_keys)
                + " — docker build args must override these for production builds"
            )

    _warn_if_local_artifacts_exist(repo_root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit .env.production before Docker preflight")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env.production"))
    parser.add_argument("--compose-file", default=str(REPO_ROOT / "docker-compose.supabase.yml"))
    parser.add_argument("--frontend-env-file", default=str(REPO_ROOT / "frontend" / ".env.production"))
    args = parser.parse_args()

    result = audit_production_env(
        env_file=Path(args.env_file).resolve(),
        compose_file=Path(args.compose_file).resolve(),
        frontend_env_file=Path(args.frontend_env_file).resolve(),
    )

    for name, ok, message in result.checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {name} - {message}")
    for warning in result.warnings:
        print(f"WARN: {warning}")

    if result.failed:
        print(f"Production env audit failed: {result.failed} issue(s)")
        return 1
    print("Production env audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
