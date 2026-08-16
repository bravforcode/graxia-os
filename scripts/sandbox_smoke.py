"""Sandbox smoke test — run the real adapters against CONFIGURED SANDBOX
credentials (no mocks). Requires MARKETPLACE_MODE=sandbox and refuses to run
otherwise. For each configured marketplace channel: poll -> import -> first
order preview + listing push preview.

Usage:
  DATABASE_URL=... MARKETPLACE_MODE=sandbox python scripts/sandbox_smoke.py
"""
import asyncio
import os
import sys

REPO = r"C:\Users\menum\graxia os"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

import graxia.packages.revenue_os.models  # noqa
from graxia.packages.revenue_os.celery.tasks.marketplace_poll import ADAPTERS
from graxia.packages.revenue_os.enums import ChannelType
from graxia.packages.revenue_os.models import ChannelConnection


async def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("FAIL: DATABASE_URL required")
        sys.exit(1)
    if os.getenv("MARKETPLACE_MODE", "sandbox") != "sandbox":
        print("FAIL: sandbox_smoke refuses to run unless MARKETPLACE_MODE=sandbox")
        sys.exit(1)

    engine = create_async_engine(url, pool_pre_ping=True)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        for channel, (adapter_cls, _reconcile) in ADAPTERS.items():
            conn = await db.scalar(select(ChannelConnection).where(
                ChannelConnection.channel == channel))
            if conn is None or not conn.enabled:
                print(f"[{channel.value}] skipped: not connected")
                continue
            if (conn.config or {}).get("mode") != "sandbox":
                print(f"[{channel.value}] skipped: mode is not sandbox "
                      f"({conn.config.get('mode')!r}) — refusing to touch live")
                continue
            adapter = adapter_cls(config=conn.config or {})
            try:
                orders = await adapter.import_orders()
                preview = orders[0] if orders else None
                print(f"[{channel.value}] POLL OK: fetched={len(orders)}")
                if preview:
                    print(f"   first: {preview['platform_order_id']} "
                          f"{preview['amount_cents']}{preview['currency']} "
                          f"status={preview['status']}")
                else:
                    print("   (no orders in sandbox)")
            except Exception as exc:
                print(f"[{channel.value}] POLL FAILED: {type(exc).__name__}: {exc}")
    await engine.dispose()
    print("\nDone. Credentials/env missing? Check .env.example Phase 2/3 block.")


if __name__ == "__main__":
    asyncio.run(main())
