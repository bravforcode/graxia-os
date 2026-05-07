import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models.base import Base
import app.models

async def init_db():
    engine = create_async_engine("sqlite+aiosqlite:///C:/Users/menum/graxia os/backend/graxia_os_production.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
