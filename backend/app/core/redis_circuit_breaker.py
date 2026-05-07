"""
Circuit Breaker Pattern สำหรับ Redis Operations
สถานะ: CLOSED (normal) → OPEN (fail fast) → HALF-OPEN (testing)
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # ทำงานปกติ
    OPEN = "open"        # Fail fast
    HALF_OPEN = "half_open"  # ทดสอบ recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5           # ทนได้กี่ครั้งถึงจะ OPEN
    recovery_timeout: float = 30.0       # รอกี่วินาทีถึง HALF-OPEN
    half_open_max_calls: int = 3       # กี่ calls ในโหมด HALF-OPEN
    success_threshold_half_open: int = 2  # ต้องสำเร็จกี่ครั้งถึง CLOSED


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker implementation for resilient service calls.
    
    Pattern:
    - CLOSED: Normal operation, failures counted
    - OPEN: Fail fast, no calls to underlying service
    - HALF_OPEN: Testing if service recovered
    """
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    
    async def call(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute operation with circuit breaker protection.
        
        Args:
            operation: Async callable to execute
            *args, **kwargs: Arguments to pass to operation
            
        Returns:
            Result from operation
            
        Raises:
            CircuitBreakerOpen: If circuit is OPEN and not ready to test
            Exception: Any exception from the operation
        """
        # Check if we should transition from OPEN to HALF_OPEN
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self.config.recovery_timeout:
                logger.info(f"[{self.name}] Transition: OPEN → HALF-OPEN")
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0
            else:
                raise CircuitBreakerOpen(
                    f"[{self.name}] Circuit is OPEN - failing fast. "
                    f"Retry after {self.config.recovery_timeout}s"
                )
        
        # Limit calls in HALF_OPEN state
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                raise CircuitBreakerOpen(
                    f"[{self.name}] HALF-OPEN limit reached ({self.config.half_open_max_calls} calls)"
                )
            self._half_open_calls += 1
        
        # Execute the operation
        try:
            result = await operation(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful operation."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold_half_open:
                logger.info(f"[{self.name}] Transition: HALF-OPEN → CLOSED")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        else:
            # Reset failure count on success in CLOSED state
            if self._failure_count > 0:
                self._failure_count = 0
    
    def _on_failure(self):
        """Handle failed operation."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN goes back to OPEN
            logger.warning(f"[{self.name}] Transition: HALF-OPEN → OPEN (failure in test)")
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.config.failure_threshold:
            logger.warning(
                f"[{self.name}] Transition: CLOSED → OPEN "
                f"({self._failure_count} failures >= {self.config.failure_threshold} threshold)"
            )
            self._state = CircuitState.OPEN
    
    def get_state(self) -> dict:
        """Get current circuit breaker state for monitoring."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": self._last_failure_time,
            "half_open_calls": self._half_open_calls,
        }
    
    def force_close(self):
        """Force circuit to CLOSED state (for manual recovery)."""
        logger.info(f"[{self.name}] Manual reset to CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is OPEN and operation is rejected."""
    pass


# Global instances for common services
redis_circuit_breaker = CircuitBreaker(
    "redis",
    CircuitBreakerConfig(
        failure_threshold=3,      # Redis should recover quickly
        recovery_timeout=10.0,    # 10 seconds to retry
        half_open_max_calls=2,
        success_threshold_half_open=1
    )
)

openclaw_circuit_breaker = CircuitBreaker(
    "openclaw",
    CircuitBreakerConfig(
        failure_threshold=5,      # Rate limits take longer
        recovery_timeout=60.0,    # 1 minute for rate limit recovery
        half_open_max_calls=1,    # Conservative in half-open
        success_threshold_half_open=1
    )
)
