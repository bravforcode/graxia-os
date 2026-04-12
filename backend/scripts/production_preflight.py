#!/usr/bin/env python3
"""Production configuration preflight for the Supabase always-on stack."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402


async def check_database() -> tuple[bool, str]:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT 1"))
            result.scalar_one()
        return True, "database reachable"
    except Exception as exc:
        return False, f"database check failed: {exc}"


async def check_redis() -> tuple[bool, str]:
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


async def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    try:
        settings.validate_production_configuration()
        checks.append(("production configuration", True, "strict settings accepted"))
    except Exception as exc:
        checks.append(("production configuration", False, str(exc)))

    checks.append(
        (
            "supabase runtime database",
            settings.IS_SUPABASE,
            f"host={settings.DATABASE_HOST or 'missing'} port={settings.DATABASE_PORT or 'default'}",
        )
    )
    checks.append(
        (
            "supabase migration database",
            settings.IS_MIGRATION_SUPABASE,
            f"host={settings.MIGRATION_DATABASE_HOST or 'missing'} port={settings.MIGRATION_DATABASE_PORT or 'default'}",
        )
    )
    checks.append(
        (
            "embedded scheduler disabled",
            not settings.SCHEDULER_EMBEDDED,
            "Celery beat should own scheduled automation in production",
        )
    )

    db_ok, db_message = await check_database()
    redis_ok, redis_message = await check_redis()
    checks.append(("database connectivity", db_ok, db_message))
    checks.append(("redis connectivity", redis_ok, redis_message))

    failed = 0
    for name, ok, message in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {name} - {message}")
        if not ok:
            failed += 1

    if failed:
        print(f"Production preflight failed: {failed} issue(s)")
        return 1
    print("Production preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
