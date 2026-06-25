"""Test database connectivity via testcontainers."""
import pytest

pytest.importorskip("testcontainers")


@pytest.mark.integration
class TestDatabaseConnection:
    async def test_postgres_connect(self, postgres_url):
        import asyncpg
        conn = await asyncpg.connect(postgres_url)
        assert conn is not None
        await conn.close()

    async def test_redis_connect(self, redis_url):
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url)
        assert await r.ping() is True
        await r.close()
