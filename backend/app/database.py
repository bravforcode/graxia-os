import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings
import tenacity

logger = logging.getLogger(__name__)

# Enterprise-grade engine with retries and connection pooling
@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    retry=tenacity.retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(f"DB connection failed, retrying... ({retry_state.attempt_number})")
)
def create_engine_with_retry():
    url = settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")
    
    engine_args = {
        "pool_pre_ping": True,
    }
    
    if is_sqlite:
        engine_args["connect_args"] = {"check_same_thread": False}
    else:
        engine_args.update({
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "connect_args": {"server_settings": {"application_name": "brav_os_mas"}}
        })

    return create_async_engine(url, **engine_args)

engine = create_engine_with_retry()
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
