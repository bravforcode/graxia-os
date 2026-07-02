from datetime import datetime, timedelta
from typing import Optional
from .event_models import EventStatus, GateState
from .event_store import EventStore
from .event_risk_gate import GateResult

class StabilizationGate:
    """Post-event stabilization: require healthy data and spread normalization before resuming."""

    def __init__(self, event_store: EventStore,
                 stabilization_minutes: int = 5,
                 require_healthy_feed: bool = True):
        self._store = event_store
        self._stabilization_minutes = stabilization_minutes
        self._require_healthy_feed = require_healthy_feed

    def is_stabilized(self, at: datetime, currency: str,
                      last_feed_healthy_at: Optional[datetime] = None,
                      spread_normal: bool = True) -> GateResult:
        """Check if post-event stabilization period has elapsed and conditions are met."""
        import hashlib, json

        recent_high_events = self._store.query_at(
            as_of=at, currency=currency, min_importance="HIGH"
        )

        relevant_events = [
            e for e in recent_high_events
            if e.status in (EventStatus.RELEASED, EventStatus.CANCELLED)
            and (at - e.scheduled_at_utc) < timedelta(minutes=self._stabilization_minutes * 3)
        ]

        if not relevant_events:
            return GateResult(
                state=GateState.CLEAR,
                event_ids=[],
                reason_codes=[],
                eligible_for_new_order_intent=True,
                evidence_hash=hashlib.sha256(b"no_recent_events").hexdigest()
            )

        event_ids = [e.event_id for e in relevant_events]
        reasons = []
        stabilized = True

        for e in relevant_events:
            elapsed = (at - e.scheduled_at_utc).total_seconds() / 60
            if elapsed < self._stabilization_minutes:
                reasons.append(f"STABILIZATION_PENDING:{e.event_name}:{elapsed:.0f}m")
                stabilized = False

            if self._require_healthy_feed:
                if last_feed_healthy_at is None or (at - last_feed_healthy_at) > timedelta(minutes=1):
                    reasons.append(f"UNHEALTHY_FEED:{e.event_name}")
                    stabilized = False

            if not spread_normal:
                reasons.append(f"SPREAD_ABNORMAL:{e.event_name}")
                stabilized = False

            if e.actual is None:
                reasons.append(f"MISSING_ACTUAL:{e.event_name}")
                stabilized = False

        state = GateState.CLEAR if stabilized else GateState.POST_EVENT_STABILIZATION

        return GateResult(
            state=state,
            event_ids=event_ids,
            reason_codes=reasons,
            eligible_for_new_order_intent=stabilized,
            evidence_hash=hashlib.sha256(
                json.dumps({"event_ids": sorted(event_ids), "stabilized": stabilized}, sort_keys=True).encode()
            ).hexdigest()
        )
