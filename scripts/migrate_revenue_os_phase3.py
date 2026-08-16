"""Phase 3 migration runner for already-deployed revenue_os databases.

Idempotent: run it multiple times safely. Handles the two things
create_all does NOT:
  1. ALTER TYPE ... ADD VALUE IF NOT EXISTS for new enum values
     (channeltype += shopee/lazada/tiktok_shop/amazon/fx,
      actiontype += affiliate)
  2. CREATE TYPE IF NOT EXISTS for brand-new enums (affiliate_status)
Tables are handled by SQLAlchemy Base.metadata.create_all (idempotent).

Usage:
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \\
    python scripts/migrate_revenue_os_phase3.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ENUM_MIGRATIONS = [
    ("channeltype", ["shopee", "lazada", "tiktok_shop", "amazon", "fx"]),
    ("actiontype", ["affiliate"]),
]


async def run() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required")
        sys.exit(1)
    import asyncpg
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        for type_name, values in ENUM_MIGRATIONS:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = $1)", type_name)
            if not exists:
                await conn.execute(f"CREATE TYPE {type_name} AS ENUM ()")
                print(f"created type {type_name}")
            for value in values:
                # DDL does not accept bind params; values are code literals above.
                await conn.execute(
                    f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'")
                print(f"  {type_name} += {value}")
        # AffiliateStatus enum is brand-new (its table is created by create_all).
        print("enum types ready")
    finally:
        await conn.close()

    # Tables + indexes via SQLAlchemy metadata (idempotent create_all)
    from sqlalchemy.ext.asyncio import create_async_engine
    from graxia.database import Base
    engine = create_async_engine(url)
    async with engine.begin() as db_conn:
        await db_conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("tables ready (create_all idempotent)")


if __name__ == "__main__":
    asyncio.run(run())
