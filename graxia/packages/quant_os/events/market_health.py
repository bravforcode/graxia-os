"""Phase BE-P3 — Market health gate."""
from enum import Enum
from dataclasses import dataclass


class HealthState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealthCheck:
    broker_identity_valid: bool = False
    feed_state: str = "UNKNOWN"
    tick_age_ms: float = float("inf")
    clock_drift_ms: float = 0.0
    spread_multiplier: float = 1.0
    session_open: bool = False
    contract_snapshot_fresh: bool = False
    risk_ledger_healthy: bool = False
    kill_switch_active: bool = False


class MarketHealthGate:
    """Market health gate. Decision eligible only if all checks pass."""

    def __init__(self, max_tick_age_ms: float = 5000, max_clock_drift_ms: float = 100,
                 max_spread_multiplier: float = 3.0):
        self._max_tick_age_ms = max_tick_age_ms
        self._max_clock_drift_ms = max_clock_drift_ms
        self._max_spread_multiplier = max_spread_multiplier
        self._state = HealthState.UNKNOWN
        self._failures: list[str] = []

    def evaluate(self, check: HealthCheck) -> HealthState:
        """Evaluate market health. All conditions must pass for HEALTHY."""
        self._failures = []

        if not check.broker_identity_valid:
            self._failures.append("broker_identity_invalid")

        if check.feed_state != "HEALTHY":
            self._failures.append(f"feed_state={check.feed_state}")

        if check.tick_age_ms > self._max_tick_age_ms:
            self._failures.append(f"tick_stale: {check.tick_age_ms:.0f}ms > {self._max_tick_age_ms}ms")

        if abs(check.clock_drift_ms) > self._max_clock_drift_ms:
            self._failures.append(f"clock_drift: {check.clock_drift_ms:.0f}ms")

        if check.spread_multiplier > self._max_spread_multiplier:
            self._failures.append(f"spread_shock: {check.spread_multiplier:.1f}x")

        if not check.session_open:
            self._failures.append("session_closed")

        if not check.contract_snapshot_fresh:
            self._failures.append("contract_snapshot_stale")

        if not check.risk_ledger_healthy:
            self._failures.append("risk_ledger_unhealthy")

        if check.kill_switch_active:
            self._failures.append("kill_switch_active")

        if self._failures:
            if len(self._failures) >= 3:
                self._state = HealthState.DISCONNECTED
            else:
                self._state = HealthState.DEGRADED
        else:
            self._state = HealthState.HEALTHY

        return self._state

    def is_healthy(self) -> bool:
        return self._state == HealthState.HEALTHY

    def get_state(self) -> HealthState:
        return self._state

    def get_failures(self) -> list[str]:
        return self._failures.copy()

    def get_summary(self) -> dict:
        return {
            "state": self._state.value,
            "is_healthy": self.is_healthy(),
            "failures": self._failures,
        }
