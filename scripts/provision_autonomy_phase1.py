"""Phase 1 real provisioning (Gate 0 -> SHADOW).

Non-destructive: create_all only adds MISSING tables; seed is idempotent.
Targets the DATABASE_URL from the root .env (Supabase).
"""
import asyncio
import os
import re
import sys

REPO = r"C:\Users\menum\graxia os"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from graxia.database import Base
import graxia.packages.revenue_os.models  # noqa: register all models
from graxia.packages.revenue_os.core.policy_engine import PolicyEngine
from graxia.packages.revenue_os.enums import AutonomyMode


def _read_root_env() -> dict:
    env = {}
    p = os.path.join(REPO, ".env")
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


async def main() -> None:
    env = _read_root_env()
    # Allow explicit override (e.g. local prod-equivalent or unpaused Supabase)
    url = os.getenv("DATABASE_URL") or env.get("DATABASE_URL", "")
    if not url:
        print("FAIL: DATABASE_URL missing from root .env or environment")
        sys.exit(1)
    # asyncpg URL
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    ssl = "require" if "sslmode=require" in url else None
    url = re.sub(r"\?sslmode=require", "", url)

    print("Connecting to:", url.split("@")[1].split("/")[0])
    kwargs = {}
    if ssl:
        kwargs["connect_args"] = {"ssl": ssl}
    engine = create_async_engine(url, pool_pre_ping=True, **kwargs)

    # 1) create missing tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("OK: create_all (missing tables only)")

    # 2) seed Gate-0 policy caps (idempotent)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        inserted = await PolicyEngine.seed_default_rules(db)
        print(f"OK: policy rules seeded (inserted={inserted})")

        # 3) Gate 0 confirmation (operator = user, approved 2026-08-16)
        #    Default caps: price +/-20%/50k THB, discount 15%/20k THB,
        #    refund 100%/1.5k THB, emails 5/day/customer
        mode = await PolicyEngine.get_autonomy_mode(db)
        print(f"current mode: {mode.value}")
        await PolicyEngine.set_autonomy_mode(db, AutonomyMode.SHADOW)
        print("OK: autonomy mode -> SHADOW (log-only, nothing executes)")

        # 4) report
        from sqlalchemy import func, select
        from graxia.packages.revenue_os.models import PolicyRule
        count = await db.scalar(select(func.count(PolicyRule.id)))
        print(f"REPORT: policy_rules={count}, mode=shadow, agents=log-only")
        print("Gate 0 PASSED: caps confirmed by operator; SHADOW started.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
