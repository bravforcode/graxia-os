"""Phase 3 real provisioning — marketplace ChannelConnection rows (idempotent).

Non-destructive: creates only MISSING rows. Mode comes from env
(MARKETPLACE_MODE=sandbox|live; default sandbox) and NEVER defaults to live —
promoting requires an explicit MARKTPLA... env / flag. The fx row is created
when missing so fx-refresh has a home.

Usage:
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
    python scripts/provision_marketplace_channels.py
"""
import asyncio
import os
import sys

REPO = r"C:\Users\menum\graxia os"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

import graxia.packages.revenue_os.models  # noqa: register all models
from graxia.packages.revenue_os.enums import ChannelType
from graxia.packages.revenue_os.models import ChannelConnection

MARKETPLACES = ["shopee", "lazada", "tiktok_shop", "amazon"]


async def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("FAIL: DATABASE_URL required (e.g. postgresql+asyncpg://...:5435/graxia_os)")
        sys.exit(1)
    mode = os.getenv("MARKETPLACE_MODE", "sandbox")
    if mode not in ("sandbox", "live"):
        print(f"FAIL: MARKETPLACE_MODE must be sandbox|live, got {mode!r}")
        sys.exit(1)

    engine = create_async_engine(url, pool_pre_ping=True)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        for name in MARKETPLACES:
            channel = ChannelType(name)
            existing = await db.scalar(select(ChannelConnection).where(
                ChannelConnection.channel == channel))
            if existing is not None:
                print(f"exists: {name} (mode={existing.config.get('mode')!r}, "
                      f"enabled={existing.enabled})")
                continue
            db.add(ChannelConnection(channel=channel, name=f"{name}-store",
                                     config={"mode": mode}))
            print(f"created: {name} (mode={mode!r})")
        fx = await db.scalar(select(ChannelConnection).where(
            ChannelConnection.channel == ChannelType.FX))
        if fx is None:
            db.add(ChannelConnection(channel=ChannelType.FX, name="fx-rates",
                                     config={"fx_rates": {}}))
            print("created: fx (rates row)")
        else:
            print("exists: fx (rates row)")
        await db.commit()

        rows = (await db.execute(select(ChannelConnection))).scalars().all()
        print("\nREPORT: channel_connections:")
        for c in rows:
            print(f"  {c.channel.value:<12} enabled={c.enabled} "
                  f"mode={c.config.get('mode', '-')}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
