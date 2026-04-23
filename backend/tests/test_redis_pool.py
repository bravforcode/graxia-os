"""
Tests for Redis Connection Pool
Production-grade connection management
"""
import inspect

import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, AsyncMock

from app.core.redis_pool import RedisPool
from app.core.redis_circuit_breaker import CircuitBreakerOpen


async def _maybe_await(value):
    if inspect.isawaitable(value):
        await value


async def _close_existing_pool_state() -> None:
    pool = RedisPool()
    client = pool._client
    connection_pool = pool._pool
    if client is not None:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            try:
                await _maybe_await(close())
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    raise
    if connection_pool is not None:
        disconnect = getattr(connection_pool, "disconnect", None)
        if disconnect is not None:
            try:
                await _maybe_await(disconnect())
            except RuntimeError as exc:
                if "Event loop is closed" not in str(exc):
                    raise
    pool._client = None
    pool._pool = None


@pytest_asyncio.fixture(autouse=True)
async def reset_redis_pool_singleton_state():
    await _close_existing_pool_state()
    yield
    await _close_existing_pool_state()


class TestRedisPoolSingleton:
    """Test RedisPool is a singleton."""

    def test_singleton_pattern(self):
        pool1 = RedisPool()
        pool2 = RedisPool()
        assert pool1 is pool2

    def test_global_instance_exists(self):
        from app.core.redis_pool import redis_pool
        assert isinstance(redis_pool, RedisPool)


class TestRedisPoolInitialization:
    """Test pool initialization and connection."""

    @pytest.mark.asyncio
    async def test_initialize_creates_pool(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_pool = Mock()
            mock_from_url.return_value = mock_pool

            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            pool = RedisPool()
            # Reset singleton state
            pool._pool = None
            pool._client = None

            await pool.initialize()

            mock_from_url.assert_called_once()
            mock_client.ping.assert_called_once()
            assert pool._pool is not None
            assert pool._client is not None

    @pytest.mark.asyncio
    async def test_initialize_handles_failure(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url:
            mock_from_url.side_effect = Exception("Connection refused")

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            with pytest.raises(Exception):
                await pool.initialize()

            assert pool._pool is None
            assert pool._client is None

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url:
            mock_from_url.return_value = Mock()

            pool = RedisPool()
            pool._pool = Mock()  # Already initialized
            pool._client = AsyncMock()

            await pool.initialize()

            # Should not create new pool
            mock_from_url.assert_not_called()


class TestRedisPoolGetClient:
    """Test getting client with circuit breaker."""

    @pytest.mark.asyncio
    async def test_get_client_returns_client_when_healthy(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_from_url.return_value = Mock()
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            client = await pool.get_client()

            assert client is not None

    @pytest.mark.asyncio
    async def test_get_client_returns_none_when_circuit_open(self):
        from app.core.redis_pool import redis_circuit_breaker

        # Force circuit open
        redis_circuit_breaker._state = CircuitBreakerOpen.__class__  # Reset first
        from app.core.redis_circuit_breaker import CircuitState
        redis_circuit_breaker._state = CircuitState.OPEN
        redis_circuit_breaker._last_failure_time = __import__('time').time()

        pool = RedisPool()
        pool._pool = Mock()
        pool._client = AsyncMock()

        client = await pool.get_client()

        # Should return None when circuit is open
        assert client is None

    @pytest.mark.asyncio
    async def test_get_client_initializes_if_not_initialized(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_from_url.return_value = Mock()
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            # Reset circuit breaker to closed state
            from app.core.redis_pool import redis_circuit_breaker
            from app.core.redis_circuit_breaker import CircuitState
            redis_circuit_breaker._state = CircuitState.CLOSED
            redis_circuit_breaker._failure_count = 0

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            client = await pool.get_client()

            # Should auto-initialize
            mock_from_url.assert_called_once()
            assert client is not None


class TestRedisPoolHealthCheck:
    """Test health checking in client retrieval."""

    @pytest.mark.asyncio
    async def test_health_check_failure_triggers_circuit_breaker(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_from_url.return_value = Mock()
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Connection lost"))
            mock_redis.return_value = mock_client

            from app.core.redis_pool import redis_circuit_breaker
            from app.core.redis_circuit_breaker import CircuitState
            redis_circuit_breaker._state = CircuitState.CLOSED
            redis_circuit_breaker._failure_count = 0

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            # First call should fail and count toward circuit breaker
            client = await pool.get_client()

            # Should return None after health check failure
            assert client is None


class TestRedisPoolClose:
    """Test graceful shutdown."""

    @pytest.mark.asyncio
    async def test_close_disconnects_pool(self):
        pool = RedisPool()
        mock_pool = AsyncMock()
        pool._pool = mock_pool
        pool._client = AsyncMock()

        await pool.close()

        mock_pool.disconnect.assert_called_once()
        assert pool._pool is None
        assert pool._client is None

    @pytest.mark.asyncio
    async def test_close_handles_none_pool(self):
        pool = RedisPool()
        pool._pool = None
        pool._client = None

        # Should not raise
        await pool.close()


class TestRedisPoolConfiguration:
    """Test pool configuration."""

    @pytest.mark.asyncio
    async def test_pool_uses_correct_settings(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_from_url.return_value = Mock()
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            await pool.initialize()

            # Check configuration
            call_kwargs = mock_from_url.call_args.kwargs
            assert call_kwargs.get('max_connections') == 20
            assert call_kwargs.get('socket_connect_timeout') == 5
            assert call_kwargs.get('socket_keepalive') is True
            assert call_kwargs.get('health_check_interval') == 30


class TestRedisPoolIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        with patch('app.core.redis_pool.ConnectionPool.from_url') as mock_from_url, \
             patch('app.core.redis_pool.aioredis.Redis') as mock_redis:

            mock_pool = AsyncMock()
            mock_from_url.return_value = mock_pool

            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_redis.return_value = mock_client

            pool = RedisPool()
            pool._pool = None
            pool._client = None

            # Initialize
            await pool.initialize()
            assert pool._client is not None

            # Get client
            client = await pool.get_client()
            assert client is not None

            # Close
            await pool.close()
            assert pool._pool is None
            assert pool._client is None
