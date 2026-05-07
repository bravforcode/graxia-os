"""
Circuit Breaker Pattern Implementation

Prevents cascade failures by stopping calls to failing services.
"""
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from typing import Any

from app.core.monitoring import metrics_collector

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation.
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Blocking calls after threshold failures
    - HALF_OPEN: Testing if service recovered
    
    Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: After 1 successful call
    - HALF_OPEN -> OPEN: After any failure
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Circuit breaker name (for logging)
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds before trying half-open
            expected_exception: Exception type to catch
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.last_success_time: datetime | None = None
        metrics_collector.set_circuit_breaker_state(self.name, 0)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        # Check if should transition to half-open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                metrics_collector.set_circuit_breaker_state(self.name, 1)
                logger.info(f"CircuitBreaker[{self.name}]: Transitioning to HALF_OPEN")
            else:
                raise CircuitBreakerError(
                    f"CircuitBreaker[{self.name}] is OPEN. "
                    f"Will retry after {self.recovery_timeout}s"
                )
        
        try:
            # Execute function
            result = func(*args, **kwargs)
            
            # Success - reset if half-open
            self._on_success()
            return result
            
        except self.expected_exception as e:
            # Failure - increment counter
            self._on_failure()
            raise e

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                metrics_collector.set_circuit_breaker_state(self.name, 1)
                logger.info(f"CircuitBreaker[{self.name}]: Transitioning to HALF_OPEN")
            else:
                raise CircuitBreakerError(
                    f"CircuitBreaker[{self.name}] is OPEN. "
                    f"Will retry after {self.recovery_timeout}s"
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to attempt reset."""
        if not self.last_failure_time:
            return True
        
        elapsed = datetime.now(UTC) - self.last_failure_time
        return elapsed.total_seconds() >= self.recovery_timeout
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self.last_success_time = datetime.now(UTC)
        
        if self.state == CircuitState.HALF_OPEN:
            # Transition to closed
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            metrics_collector.set_circuit_breaker_state(self.name, 0)
            logger.info(f"CircuitBreaker[{self.name}]: Recovered, transitioning to CLOSED")
        
        # Reset failure count on success in closed state
        if self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(UTC)
        
        logger.warning(
            f"CircuitBreaker[{self.name}]: Failure {self.failure_count}/{self.failure_threshold}"
        )
        
        # Transition to open if threshold reached
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            metrics_collector.set_circuit_breaker_state(self.name, 2)
            logger.error(
                f"CircuitBreaker[{self.name}]: Threshold reached, transitioning to OPEN. "
                f"Will retry after {self.recovery_timeout}s"
            )
        
        # If half-open, go back to open immediately
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            metrics_collector.set_circuit_breaker_state(self.name, 2)
            logger.warning(f"CircuitBreaker[{self.name}]: Failed in HALF_OPEN, back to OPEN")
    
    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        metrics_collector.set_circuit_breaker_state(self.name, 0)
        logger.info(f"CircuitBreaker[{self.name}]: Manually reset to CLOSED")
    
    def get_state(self) -> dict:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "recovery_timeout": self.recovery_timeout
        }


def circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: int = 60,
    expected_exception: type = Exception
):
    """
    Decorator for circuit breaker pattern.
    
    Usage:
        @circuit_breaker(name="external_api", failure_threshold=3)
        async def call_external_api():
            ...
    """
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception
    )
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call_async(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Global circuit breakers registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """
    Get or create circuit breaker by name.
    
    Args:
        name: Circuit breaker name
        **kwargs: CircuitBreaker initialization parameters
    
    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, dict]:
    """Get state of all circuit breakers."""
    return {
        name: breaker.get_state()
        for name, breaker in _circuit_breakers.items()
    }


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    for breaker in _circuit_breakers.values():
        breaker.reset()
