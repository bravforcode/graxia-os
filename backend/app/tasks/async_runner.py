"""Run coroutines from sync Celery tasks."""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.database import engine

T = TypeVar("T")


async def _run_and_release_pool(coro: Coroutine[Any, Any, T]) -> T:
    try:
        return await coro
    finally:
        # asyncpg connections belong to the loop that opened them, and asyncio.run closes that loop.
        # Drop the pool before it closes so the next task does not reuse a dead connection.
        await engine.dispose()

        # Clean up async Redis connections tied to this loop
        try:
            from app.core.openclaw import openclaw_client

            if openclaw_client._redis is not None:
                await openclaw_client._redis.aclose()
                openclaw_client._redis = None
        except Exception:
            pass

        try:
            from app.core.redis_pool import redis_pool

            if redis_pool.is_initialized():
                await redis_pool.close()
        except Exception:
            pass


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(_run_and_release_pool(coro))
