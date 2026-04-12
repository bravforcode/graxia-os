from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

engine_kwargs: dict[str, Any] = {
    "echo": settings.APP_ENV == "development",
    "pool_pre_ping": True,
}
connect_args: dict[str, Any] = {}

if settings.IS_SUPABASE_TRANSACTION_MODE:
    engine_kwargs["poolclass"] = NullPool
    connect_args["statement_cache_size"] = 0
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

if connect_args:
    engine_kwargs["connect_args"] = connect_args

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
