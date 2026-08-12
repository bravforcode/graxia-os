"""Phase 6 — Market health gate for shadow mode."""
from dataclasses import dataclass
from enum import Enum


class MarketHealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


@dataclass
class MarketHealthCheck:
    feed_healthy: bool
    clock_ok: bool
    spread_ok: bool
    session_ok: bool
    state: MarketHealthState


class MarketHealthMachine:
    def __init__(self):
        self.state = MarketHealthState.HEALTHY

    def check(self, feed_ok: bool, clock_ok: bool, spread_ok: bool, session_ok: bool) -> MarketHealthCheck:
        if not feed_ok:
            self.state = MarketHealthState.DISCONNECTED
        elif not all([clock_ok, spread_ok, session_ok]):
            self.state = MarketHealthState.DEGRADED
        else:
            self.state = MarketHealthState.HEALTHY

        return MarketHealthCheck(
            feed_healthy=feed_ok,
            clock_ok=clock_ok,
            spread_ok=spread_ok,
            session_ok=session_ok,
            state=self.state,
        )

    def is_healthy(self) -> bool:
        return self.state == MarketHealthState.HEALTHY
