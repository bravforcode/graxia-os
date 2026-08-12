#!/usr/bin/env python3
"""Print the current Alembic migration version from the configured database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        version = result.scalar()
    if not version:
        print("unknown")
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
