"""
Production-grade Redis Client with Connection Pooling
แก้ปัญหา: Connection ไม่ reuse, latency สูง, resource leak
"""
import logging
from functools import lru_cache
from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from app.config import settings
from app.core.redis_circuit_breaker import CircuitBreakerOpen, redis_circuit_breaker

logger = logging.getLogger(__name__)


class RedisPool:
    """
    Singleton Redis connection pool manager.

    Features:
    - Connection pooling (max 20 connections)
    - Connection reuse (reduces latency)
    - Circuit breaker integration
    - Health checks every 30 seconds
    - Automatic reconnection
    """

    _instance: Optional['RedisPool'] = None
    _pool: ConnectionPool | None = None
    _client: aioredis.Redis | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """
        Initialize connection pool.

        Creates a connection pool with:
        - 20 max connections
        - 5s connection timeout
        - Keepalive enabled
        - Health checks every 30s
        """
        if self._pool is not None:
            return

        try:
            self._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)

            # Verify connection
            await self._client.ping()
            logger.info("Redis pool initialized successfully")

        except Exception as e:
            logger.error(f"Redis pool initialization failed: {e}")
            self._pool = None
            self._client = None
            raise

    async def get_client(self) -> aioredis.Redis | None:
        """
        Get Redis client with circuit breaker protection.

        Returns:
            Redis client if healthy, None otherwise
        """
        if self._client is None:
            try:
                await self.initialize()
            except Exception as e:
                logger.warning(f"Redis initialization failed: {e}")
                return None

        try:
            return await redis_circuit_breaker.call(self._get_client_safe)
        except CircuitBreakerOpen:
            logger.debug("Redis circuit breaker is OPEN - using fallback")
            return None
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return None

    async def _get_client_safe(self) -> aioredis.Redis:
        """Internal method to get client with health check."""
        if self._client is None:
            raise RuntimeError("Redis not initialized")

        # Health check before returning
        await self._client.ping()
        return self._client

    async def close(self):
        """Clean shutdown of connection pool."""
        if self._pool:
            try:
                await self._pool.disconnect()
                logger.info("Redis pool closed")
            except Exception as e:
                logger.warning(f"Error closing Redis pool: {e}")
            finally:
                self._pool = None
                self._client = None

    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self._pool is not None and self._client is not None

    async def health_status(self) -> dict:
        """Get current health status for monitoring."""
        status = {
            "initialized": self.is_initialized(),
            "circuit_state": redis_circuit_breaker.get_state(),
        }

        if self._client:
            try:
                await self._client.ping()
                status["ping"] = "ok"
                status["healthy"] = True
            except Exception as e:
                status["ping"] = f"failed: {e}"
                status["healthy"] = False
        else:
            status["ping"] = "not_initialized"
            status["healthy"] = False

        return status


# Global instance
redis_pool = RedisPool()


# Convenience functions for common operations
async def get_redis() -> aioredis.Redis | None:
    """Get Redis client (convenience function)."""
    return await redis_pool.get_client()


@lru_cache
def get_redis_client() -> aioredis.Redis:
    """Redis client for cache, metrics, session store"""
    if settings.REDIS_URL:
        return aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
    
    return aioredis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )


@lru_cache
def get_redis_pool() -> aioredis.Redis:
    """Redis pool for Arq job queue (separate connection pool)"""
    if settings.REDIS_URL:
        return aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=10,
            socket_keepalive=True,
            health_check_interval=30,
        )

    return aioredis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=10,
        socket_keepalive=True,
        health_check_interval=30,
    )


async def ping_redis() -> bool:
    """Health check for Redis"""
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception:
        return False


# Alias for backward compatibility with tests
RedisPoolClass = get_redis_pool


async def redis_health() -> dict:
    """Quick health check."""
    return await redis_pool.health_status()
