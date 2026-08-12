import asyncio

from app.config import settings

print(f"DATABASE_URL: {settings.DATABASE_URL}")
from app.database import engine
from app.models.base import Base


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created")


if __name__ == "__main__":
    asyncio.run(init())
