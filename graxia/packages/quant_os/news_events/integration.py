from datetime import datetime
from typing import Optional
from .event_store import EventStore
from .event_risk_gate import EventRiskGate, GateResult
from .stabilization_gate import StabilizationGate
from .event_models import GateState

class NewsEventIntegration:
    """
    Ties event risk gate into execution pipeline.
    Used by BacktestEngine and live readiness to check event gate before order submission.
    """

    def __init__(self, event_store: EventStore, pre_block_minutes: int = 30,
                 post_block_minutes: int = 15, stabilization_minutes: int = 5):
        self._store = event_store
        self._risk_gate = EventRiskGate(event_store, pre_block_minutes, post_block_minutes)
        self._stabilization_gate = StabilizationGate(event_store, stabilization_minutes)

    def can_submit_order(self, at: datetime, currency: str,
                          last_feed_healthy_at: Optional[datetime] = None,
                          spread_normal: bool = True) -> GateResult:
        """
        Full gate check: event risk + post-event stabilization.
        Returns GateResult with eligible_for_new_order_intent=True only if ALL checks pass.
        """
        risk_result = self._risk_gate.evaluate(at=at, currency=currency)

        if risk_result.state != GateState.CLEAR:
            return risk_result

        stab_result = self._stabilization_gate.is_stabilized(
            at=at, currency=currency,
            last_feed_healthy_at=last_feed_healthy_at,
            spread_normal=spread_normal
        )

        if stab_result.state == GateState.CLEAR:
            return risk_result

        return stab_result

    def get_gate_state(self, at: datetime, currency: str) -> GateState:
        """Quick check returning only the gate state."""
        result = self.can_submit_order(at=at, currency=currency)
        return result.state

    def record_event(self, event) -> None:
        """Add an event to the underlying store."""
        self._store.add_event(event)

    @property
    def store(self) -> EventStore:
        return self._store
