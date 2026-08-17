"""Migration runner for Revenue OS billing (P2-10).

Adds the revenue_os_subscriptions table. Idempotent — safe to re-run.

Usage (PowerShell):
    $env:DATABASE_URL="postgresql+asyncpg://graxia:graxia@localhost:5436/graxia_os"
    python scripts/migrate_revenue_os_billing.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine

from graxia.database import Base
from graxia.packages.revenue_os import models  # noqa: F401  (register tables)
from graxia.packages.revenue_os.db import DATABASE_URL


async def run() -> None:
    print(f"[migrate-billing] DATABASE_URL host: {DATABASE_URL.split('@')[-1]}")
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    print("[migrate-billing] tables ready (create_all idempotent) — "
          "revenue_os_subscriptions created if missing")


if __name__ == "__main__":
    asyncio.run(run())