import asyncio
from app.models import Base
from sqlalchemy.ext.asyncio import create_async_engine
import os

DB_URL = "sqlite+aiosqlite:///C:/Users/menum/graxia_viewing.db"

async def init():
    print(f"Creating local DB at {DB_URL}...")
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("✅ Local DB initialized.")

if __name__ == "__main__":
    asyncio.run(init())
