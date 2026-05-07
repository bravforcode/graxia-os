#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterable
from pathlib import Path

import httpx
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.database import AsyncSessionLocal

from scripts.production_env_audit import audit_production_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-runtime", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env.production"))
    parser.add_argument("--compose-file", default=str(REPO_ROOT / "docker-compose.prod.yml"))
    parser.add_argument(
        "--frontend-env-file", default=str(REPO_ROOT / "frontend" / ".env.production")
    )
    return parser.parse_args()


def _check_file_set(paths: Iterable[Path]) -> tuple[bool, list[str]]:
    missing = [str(path) for path in paths if not path.exists()]
    return (not missing, missing)


async def _check_db() -> tuple[bool, str]:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True, "database reachable"
    except Exception as exc:
        return False, f"database check failed: {exc}"


async def _check_redis() -> tuple[bool, str]:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True, "redis reachable"
    except Exception as exc:
        return False, f"redis check failed: {exc}"


async def _check_health(base_url: str) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, headers={"accept": "application/json"})
            payload = response.json()
        readiness = payload.get("readiness", {})
        mode = readiness.get("mode", "unknown")
        ok = response.status_code == 200 and mode in {"full", "degraded"}
        return ok, f"status={response.status_code} mode={mode}"
    except Exception as exc:
        return False, f"health check failed: {exc}"


async def main() -> int:
    args = parse_args()
    checks: list[tuple[str, bool, str]] = []
    warnings: list[str] = []

    if args.strict:
        audit = audit_production_env(
            env_file=Path(args.env_file).resolve(),
            compose_file=Path(args.compose_file).resolve(),
            frontend_env_file=Path(args.frontend_env_file).resolve(),
            repo_root=REPO_ROOT,
        )
        checks.extend((f"env-audit::{name}", ok, detail) for name, ok, detail in audit.checks)
        warnings.extend(audit.warnings)
    else:
        checks.append(("production-config", True, "skipped (non-strict)"))

    required_ops_files = [
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
        REPO_ROOT / ".github" / "workflows" / "security-gate.yml",
        REPO_ROOT / ".github" / "workflows" / "deploy.yml",
        REPO_ROOT / "deploy" / "monitoring" / "prometheus.yml",
        REPO_ROOT / "deploy" / "monitoring" / "alertmanager.yml",
        REPO_ROOT / "deploy" / "monitoring" / "slos.yml",
        REPO_ROOT / "deploy" / "scripts" / "deploy.sh",
        REPO_ROOT / "deploy" / "scripts" / "rollback.sh",
        REPO_ROOT / "deploy" / "scripts" / "dr-rebuild.sh",
        BACKEND_ROOT / "scripts" / "backup_database.py",
        BACKEND_ROOT / "scripts" / "restore_database.py",
        BACKEND_ROOT / "scripts" / "smoke_tests.sh",
    ]
    files_ok, missing = _check_file_set(required_ops_files)
    checks.append(
        (
            "ops-artifacts",
            files_ok,
            "all required files present" if files_ok else f"missing: {', '.join(missing)}",
        )
    )

    if not args.skip_runtime:
        db_ok, db_msg = await _check_db()
        redis_ok, redis_msg = await _check_redis()
        health_ok, health_msg = await _check_health(args.base_url)
        checks.append(("database", db_ok, db_msg))
        checks.append(("redis", redis_ok, redis_msg))
        checks.append(("backend-health", health_ok, health_msg))

    failed = 0
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name} - {detail}")
        if not ok:
            failed += 1
    for warning in warnings:
        print(f"WARN: {warning}")

    summary = {"failed": failed, "total": len(checks), "strict": bool(args.strict)}
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
