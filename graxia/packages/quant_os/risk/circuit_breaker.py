"""
Circuit Breaker System

Soft stop mechanism that temporarily halts trading under specific conditions.
Unlike kill switch, circuit breaker can auto-reset after cooldown.

Circuit breaker conditions:
- Consecutive losses (loss streak)
- Volatility spike
- Slippage exceedance
- Error rate threshold
- Manual temporary halt

States: CLOSED (normal) → OPEN (blocked) → HALF_OPEN (testing)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from enum import Enum


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"         # Trading blocked
    HALF_OPEN = "HALF_OPEN"  # Testing if condition resolved


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    # Loss streak
    max_consecutive_losses: int = 3
    
    # Volatility
    volatility_spike_threshold: float = 3.0  # Multiple of average
    
    # Slippage
    max_slippage_pips: float = 5.0
    
    # Error rate
    max_error_rate_pct: float = 20.0
    error_window_minutes: int = 10
    
    # Cooldown
    cooldown_minutes: int = 30
    
    # Half-open test
    test_trades_on_half_open: int = 1


class CircuitBreaker:
    """
    Circuit breaker for temporary trading halts.
    
    Unlike kill switch (manual reset required), circuit breaker:
    - Auto-resets after cooldown
    - Can test with small trades (half-open state)
    - Tracks multiple conditions
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        
        # Tracking
        self.consecutive_losses: int = 0
        self.error_count: int = 0
        self.total_count: int = 0
        self.error_window_start: Optional[datetime] = None
        
        # State tracking
        self.opened_at: Optional[datetime] = None
        self.opened_reason: str = ""
        self.test_trades_remaining: int = 0
        
        # History
        self.slippage_history: List[float] = []
    
    @property
    def is_blocked(self) -> bool:
        """Check if trading is currently blocked"""
        return self.state == CircuitBreakerState.OPEN
    
    @property
    def is_triggered(self) -> bool:
        """Alias for is_blocked"""
        return self.is_blocked
    
    @property
    def reason(self) -> str:
        """Current circuit breaker reason"""
        if self.state == CircuitBreakerState.OPEN:
            return self.opened_reason
        return ""
    
    def record_trade(
        self,
        pnl: float,
        slippage_pips: float = 0.0,
        is_error: bool = False
    ) -> Optional[CircuitBreakerState]:
        """
        Record a trade outcome and check if circuit breaker should trip.
        
        Returns:
            New state if changed, None otherwise
        """
        # Track errors
        self._track_error(is_error)
        
        # Track slippage
        self.slippage_history.append(slippage_pips)
        if len(self.slippage_history) > 20:
            self.slippage_history.pop(0)
        
        # Update consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Check if should open
        if self.state == CircuitBreakerState.CLOSED:
            return self._check_open_conditions()
        
        # Check if should close (half-open testing)
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.test_trades_remaining -= 1
            if self.test_trades_remaining <= 0 and pnl >= 0:
                return self._close_circuit("Test trades successful")
            elif pnl < 0:
                return self._open_circuit("Test trade failed - reopening")
        
        return None
    
    def _track_error(self, is_error: bool) -> None:
        """Track error rate"""
        now = datetime.now(timezone.utc)
        
        # Reset window if needed
        if self.error_window_start is None or \
           now - self.error_window_start > timedelta(minutes=self.config.error_window_minutes):
            self.error_window_start = now
            self.error_count = 0
            self.total_count = 0
        
        self.total_count += 1
        if is_error:
            self.error_count += 1
    
    def _check_open_conditions(self) -> Optional[CircuitBreakerState]:
        """Check if circuit should open"""
        # Check consecutive losses
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            return self._open_circuit(
                f"{self.consecutive_losses} consecutive losses"
            )
        
        # Check slippage
        if self.slippage_history:
            recent_slippage = sum(self.slippage_history[-5:]) / len(self.slippage_history[-5:])
            if recent_slippage > self.config.max_slippage_pips:
                return self._open_circuit(
                    f"High slippage: {recent_slippage:.1f} pips"
                )
        
        # Check error rate
        if self.total_count > 5:  # Minimum sample size
            error_rate = (self.error_count / self.total_count) * 100
            if error_rate > self.config.max_error_rate_pct:
                return self._open_circuit(
                    f"High error rate: {error_rate:.1f}%"
                )
        
        return None
    
    def _open_circuit(self, reason: str) -> CircuitBreakerState:
        """Open the circuit"""
        self.state = CircuitBreakerState.OPEN
        self.opened_at = datetime.now(timezone.utc)
        self.opened_reason = reason
        return self.state
    
    def _close_circuit(self, reason: str) -> CircuitBreakerState:
        """Close the circuit"""
        self.state = CircuitBreakerState.CLOSED
        self.opened_at = None
        self.opened_reason = ""
        self.consecutive_losses = 0
        self.error_count = 0
        self.total_count = 0
        return self.state
    
    def check_cooldown(self) -> Optional[CircuitBreakerState]:
        """
        Check if cooldown period has passed for auto-reset.
        Call periodically (e.g., every minute).
        """
        if self.state != CircuitBreakerState.OPEN:
            return None
        
        if self.opened_at is None:
            return None
        
        elapsed = datetime.now(timezone.utc) - self.opened_at
        cooldown = timedelta(minutes=self.config.cooldown_minutes)
        
        if elapsed >= cooldown:
            # Transition to half-open for testing
            self.state = CircuitBreakerState.HALF_OPEN
            self.test_trades_remaining = self.config.test_trades_on_half_open
            return self.state
        
        return None
    
    def manual_halt(self, reason: str) -> CircuitBreakerState:
        """Manual temporary halt"""
        return self._open_circuit(f"Manual halt: {reason}")
    
    def manual_resume(self) -> CircuitBreakerState:
        """Manual resume"""
        return self._close_circuit("Manual resume")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status"""
        elapsed = None
        if self.opened_at and self.state == CircuitBreakerState.OPEN:
            elapsed = (datetime.now(timezone.utc) - self.opened_at).total_seconds() / 60
        
        error_rate = 0.0
        if self.total_count > 0:
            error_rate = (self.error_count / self.total_count) * 100
        
        return {
            "state": self.state.value,
            "is_blocked": self.is_blocked,
            "reason": self.opened_reason,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "cooldown_elapsed_minutes": elapsed,
            "consecutive_losses": self.consecutive_losses,
            "error_rate_pct": error_rate,
            "avg_slippage_pips": sum(self.slippage_history[-5:]) / len(self.slippage_history[-5:]) if self.slippage_history else 0,
        }


class MultiCircuitBreaker:
    """Multiple circuit breakers for different conditions"""
    
    def __init__(self):
        # Loss streak circuit breaker
        self.loss_cb = CircuitBreaker(CircuitBreakerConfig(
            max_consecutive_losses=3,
            cooldown_minutes=30
        ))
        
        # Slippage circuit breaker
        self.slippage_cb = CircuitBreaker(CircuitBreakerConfig(
            max_slippage_pips=5.0,
            cooldown_minutes=60
        ))
        
        # Error rate circuit breaker
        self.error_cb = CircuitBreaker(CircuitBreakerConfig(
            max_error_rate_pct=20.0,
            cooldown_minutes=15
        ))
    
    def record_trade(self, pnl: float, slippage_pips: float = 0.0, is_error: bool = False) -> None:
        """Record trade across all circuit breakers"""
        self.loss_cb.record_trade(pnl, slippage_pips, is_error)
        self.slippage_cb.record_trade(pnl, slippage_pips, is_error)
        self.error_cb.record_trade(pnl, slippage_pips, is_error)
    
    @property
    def is_blocked(self) -> bool:
        """Check if any circuit breaker is open"""
        return self.loss_cb.is_blocked or self.slippage_cb.is_blocked or self.error_cb.is_blocked
    
    def get_blocking_reason(self) -> str:
        """Get reason for block"""
        reasons = []
        if self.loss_cb.is_blocked:
            reasons.append(f"Losses: {self.loss_cb.reason}")
        if self.slippage_cb.is_blocked:
            reasons.append(f"Slippage: {self.slippage_cb.reason}")
        if self.error_cb.is_blocked:
            reasons.append(f"Errors: {self.error_cb.reason}")
        return "; ".join(reasons) if reasons else ""
    
    def check_cooldowns(self) -> None:
        """Check all circuit breakers for cooldown"""
        self.loss_cb.check_cooldown()
        self.slippage_cb.check_cooldown()
        self.error_cb.check_cooldown()
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        return {
            "is_blocked": self.is_blocked,
            "blocking_reason": self.get_blocking_reason(),
            "loss_circuit": self.loss_cb.get_status(),
            "slippage_circuit": self.slippage_cb.get_status(),
            "error_circuit": self.error_cb.get_status(),
        }
