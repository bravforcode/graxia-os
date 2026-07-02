"""Phase BE-P3 — Unified event risk gate. Combines event + market health."""

from datetime import datetime

from .event_gate import EventGate, EventRecord, GateState
from .market_health import HealthCheck, HealthState, MarketHealthGate


class EventRiskGate:
    """Unified gate: blocks entries if event OR market health fails."""

    def __init__(self, event_gate: EventGate = None, health_gate: MarketHealthGate = None):
        self._event_gate = event_gate or EventGate()
        self._health_gate = health_gate or MarketHealthGate()
        self._block_reasons: list[str] = []

    def evaluate(
        self, now_utc: datetime, pending_events: list[EventRecord], health_check: HealthCheck
    ) -> tuple[bool, list[str]]:
        self._block_reasons = []

        event_state = self._event_gate.evaluate(now_utc, pending_events)
        if event_state != GateState.CLEAR:
            self._block_reasons.append(f"event_gate: {event_state.value}")

        health_state = self._health_gate.evaluate(health_check)
        if health_state != HealthState.HEALTHY:
            self._block_reasons.append(f"market_health: {health_state.value}")
            self._block_reasons.extend(self._health_gate.get_failures())

        eligible = len(self._block_reasons) == 0
        return eligible, self._block_reasons

    def is_blocking(self) -> bool:
        return len(self._block_reasons) > 0

    def get_block_reasons(self) -> list[str]:
        return self._block_reasons.copy()

    def get_event_state(self) -> GateState:
        return self._event_gate.get_state()

    def get_health_state(self) -> HealthState:
        return self._health_gate.get_state()

    def get_summary(self) -> dict:
        return {
            "eligible": not self.is_blocking(),
            "block_reasons": self._block_reasons,
            "event_state": self.get_event_state().value,
            "health_state": self.get_health_state().value,
        }
