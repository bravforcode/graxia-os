"""
Tests for Circuit Breaker
"""
import pytest
import asyncio
from app.core.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker instance."""
        return CircuitBreaker(
            name="test_breaker",
            failure_threshold=3,
            recovery_timeout=1  # 1 second for faster tests
        )
    
    def test_initial_state_is_closed(self, circuit_breaker):
        """Test that initial state is CLOSED."""
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
    
    def test_successful_call_in_closed_state(self, circuit_breaker):
        """Test successful call in CLOSED state."""
        def success_func():
            return "success"
        
        result = circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
    
    def test_failed_call_increments_counter(self, circuit_breaker):
        """Test that failed call increments failure counter."""
        def fail_func():
            raise Exception("Test failure")
        
        with pytest.raises(Exception):
            circuit_breaker.call(fail_func)
        
        assert circuit_breaker.failure_count == 1
        assert circuit_breaker.state == CircuitState.CLOSED
    
    def test_opens_after_threshold_failures(self, circuit_breaker):
        """Test that circuit opens after threshold failures."""
        def fail_func():
            raise Exception("Test failure")
        
        # Fail 3 times (threshold)
        for _ in range(3):
            with pytest.raises(Exception):
                circuit_breaker.call(fail_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.failure_count == 3
    
    def test_blocks_calls_when_open(self, circuit_breaker):
        """Test that calls are blocked when circuit is OPEN."""
        def fail_func():
            raise Exception("Test failure")
        
        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                circuit_breaker.call(fail_func)
        
        # Try to call again - should be blocked
        def success_func():
            return "success"
        
        with pytest.raises(CircuitBreakerError):
            circuit_breaker.call(success_func)
    
    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, circuit_breaker):
        """Test transition to HALF_OPEN after recovery timeout."""
        def fail_func():
            raise Exception("Test failure")
        
        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                circuit_breaker.call(fail_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # Next call should transition to HALF_OPEN
        def success_func():
            return "success"
        
        result = circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
    
    def test_half_open_to_closed_on_success(self, circuit_breaker):
        """Test transition from HALF_OPEN to CLOSED on success."""
        # Manually set to HALF_OPEN
        circuit_breaker.state = CircuitState.HALF_OPEN
        
        def success_func():
            return "success"
        
        result = circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
    
    def test_half_open_to_open_on_failure(self, circuit_breaker):
        """Test transition from HALF_OPEN to OPEN on failure."""
        # Manually set to HALF_OPEN
        circuit_breaker.state = CircuitState.HALF_OPEN
        
        def fail_func():
            raise Exception("Test failure")
        
        with pytest.raises(Exception):
            circuit_breaker.call(fail_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
    
    def test_manual_reset(self, circuit_breaker):
        """Test manual reset of circuit breaker."""
        def fail_func():
            raise Exception("Test failure")
        
        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                circuit_breaker.call(fail_func)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Manual reset
        circuit_breaker.reset()
        
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
    
    def test_get_state(self, circuit_breaker):
        """Test getting circuit breaker state."""
        state = circuit_breaker.get_state()
        
        assert "name" in state
        assert "state" in state
        assert "failure_count" in state
        assert "failure_threshold" in state
        assert state["name"] == "test_breaker"
        assert state["state"] == "closed"
