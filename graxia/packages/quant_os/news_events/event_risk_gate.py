"""Event risk gate for news events.

.. deprecated::
    Use ``shadow.event_risk_gate.EventRiskGate`` instead.
    This module will be removed in a future release.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .event_models import EventStatus, GateState
from .event_store import EventStore


@dataclass
class GateResult:
    state: GateState
    event_ids: list[str]
    reason_codes: list[str]
    eligible_for_new_order_intent: bool
    evidence_hash: str


class EventRiskGate:
    def __init__(self, event_store: EventStore, pre_block_minutes: int = 30, post_block_minutes: int = 15):
        self._store = event_store
        self._pre_block_minutes = pre_block_minutes
        self._post_block_minutes = post_block_minutes

    def evaluate(self, at: datetime, currency: str | None = None) -> GateResult:
        events = self._store.query_at(as_of=at, currency=currency, min_importance="HIGH")

        active_events = []
        for e in events:
            if e.status in (EventStatus.SCHEDULED, EventStatus.DELAYED):
                window_start = e.scheduled_at_utc - timedelta(minutes=self._pre_block_minutes)
                window_end = e.scheduled_at_utc + timedelta(minutes=self._post_block_minutes)
                if window_start <= at <= window_end:
                    active_events.append(e)
            elif e.status == EventStatus.RELEASED:
                if e.actual is None:
                    active_events.append(e)

        if not active_events:
            return GateResult(
                state=GateState.CLEAR,
                event_ids=[],
                reason_codes=[],
                eligible_for_new_order_intent=True,
                evidence_hash=self._hash_result([], GateState.CLEAR),
            )

        event_ids = [e.event_id for e in active_events]
        state = GateState.EVENT_BLOCK
        reason_codes = []

        for e in active_events:
            if e.status in (EventStatus.SCHEDULED, EventStatus.DELAYED):
                reason_codes.append(f"PRE_EVENT_BLOCK:{e.event_name}")
            elif e.actual is None:
                reason_codes.append(f"MISSING_ACTUAL:{e.event_name}")

        return GateResult(
            state=state,
            event_ids=event_ids,
            reason_codes=reason_codes,
            eligible_for_new_order_intent=False,
            evidence_hash=self._hash_result(event_ids, state),
        )

    def _hash_result(self, event_ids: list[str], state: GateState) -> str:
        import hashlib
        import json

        data = json.dumps({"event_ids": sorted(event_ids), "state": state.value}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
