"""
Tests for Redis Circuit Breaker Pattern
TDD: Write tests first, then implement
"""
import pytest
import time
from unittest.mock import Mock, AsyncMock

from app.core.redis_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpen,
)


class TestCircuitBreakerConfig:
    """Test configuration defaults."""

    def test_default_config(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 30.0
        assert config.half_open_max_calls == 3
        assert config.success_threshold_half_open == 2


class TestCircuitBreakerStateTransitions:
    """Test state machine transitions: CLOSED → OPEN → HALF_OPEN → CLOSED"""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_closed_to_open_on_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        
        mock_op = AsyncMock(side_effect=Exception("fail"))
        
        # 3 failures should trigger OPEN
        for i in range(3):
            with pytest.raises(Exception):
                await cb.call(mock_op)
        
        assert cb._state == CircuitState.OPEN
        assert cb._failure_count == 3

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1  # 100ms for fast test
        ))
        
        # Trigger OPEN
        mock_op = AsyncMock(side_effect=Exception("fail"))
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(mock_op)
        
        assert cb._state == CircuitState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Next call should transition to HALF_OPEN
        mock_success = AsyncMock(return_value="success")
        result = await cb.call(mock_success)
        
        assert cb._state == CircuitState.HALF_OPEN
        assert result == "success"

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=3,
            success_threshold_half_open=2
        ))
        
        # Set to HALF_OPEN manually
        cb._state = CircuitState.HALF_OPEN
        cb._half_open_calls = 0
        cb._success_count = 0
        
        # 2 successful calls should transition to CLOSED
        mock_op = AsyncMock(return_value="success")
        await cb.call(mock_op)
        await cb.call(mock_op)
        
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1
        ))
        
        # Set to HALF_OPEN
        cb._state = CircuitState.HALF_OPEN
        
        # 1 failure in HALF_OPEN should go back to OPEN
        mock_op = AsyncMock(side_effect=Exception("fail"))
        with pytest.raises(Exception):
            await cb.call(mock_op)
        
        assert cb._state == CircuitState.OPEN


class TestCircuitBreakerFailFast:
    """Test that OPEN state fails fast without calling operation."""

    @pytest.mark.asyncio
    async def test_open_state_fails_fast(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        cb._state = CircuitState.OPEN
        cb._last_failure_time = time.time()
        
        mock_op = AsyncMock(return_value="should_not_call")
        
        with pytest.raises(CircuitBreakerOpen):
            await cb.call(mock_op)
        
        mock_op.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_open_limits_calls(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            half_open_max_calls=2
        ))
        cb._state = CircuitState.HALF_OPEN
        cb._half_open_calls = 2  # Already at limit
        
        mock_op = AsyncMock(return_value="success")
        
        with pytest.raises(CircuitBreakerOpen):
            await cb.call(mock_op)


class TestCircuitBreakerStateReporting:
    """Test state reporting for monitoring."""

    @pytest.mark.asyncio
    async def test_get_state_returns_dict(self):
        cb = CircuitBreaker("test")
        state = cb.get_state()
        
        assert "state" in state
        assert "failure_count" in state
        assert "success_count" in state
        assert "last_failure" in state
        assert "half_open_calls" in state

    @pytest.mark.asyncio
    async def test_state_reflects_current_condition(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        
        # Initial state
        assert cb.get_state()["state"] == "closed"
        
        # After failures
        mock_op = AsyncMock(side_effect=Exception("fail"))
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(mock_op)
        
        assert cb.get_state()["state"] == "open"
        assert cb.get_state()["failure_count"] == 2


class TestCircuitBreakerSuccessReset:
    """Test that successes reset failure count."""

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))
        cb._failure_count = 3
        
        mock_op = AsyncMock(return_value="success")
        await cb.call(mock_op)
        
        assert cb._failure_count == 0


class TestRealWorldScenarios:
    """Test scenarios matching real Redis/OpenClaw failures."""

    @pytest.mark.asyncio
    async def test_redis_network_timeout_scenario(self):
        """Simulate Redis network timeout recovery."""
        cb = CircuitBreaker("redis", CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=10.0
        ))
        
        # Simulate 3 timeouts
        timeout_op = AsyncMock(side_effect=TimeoutError("Connection timeout"))
        for _ in range(3):
            with pytest.raises(TimeoutError):
                await cb.call(timeout_op)
        
        # Circuit should be OPEN
        assert cb._state == CircuitState.OPEN
        
        # Fast-forward time (simulate waiting)
        cb._last_failure_time = time.time() - 11  # Past recovery timeout
        
        # Now should work
        working_op = AsyncMock(return_value={"connected": True})
        result = await cb.call(working_op)
        
        assert result == {"connected": True}

    @pytest.mark.asyncio
    async def test_openclaw_rate_limit_scenario(self):
        """Simulate OpenClaw rate limit with longer recovery."""
        cb = CircuitBreaker("openclaw", CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60.0  # Longer for rate limits
        ))
        
        # Simulate rate limit errors
        rate_limit_op = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )
        for _ in range(5):
            with pytest.raises(Exception):
                await cb.call(rate_limit_op)
        
        assert cb._state == CircuitState.OPEN
        assert cb._last_failure_time > 0
