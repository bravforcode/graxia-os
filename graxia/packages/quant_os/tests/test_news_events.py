"""Tests for news_events modules — event models, event store, event risk gate."""

import pytest
from datetime import datetime, timezone, timedelta
from dataclasses import replace

from graxia.packages.quant_os.news_events.event_models import (
    EconomicEvent, EventImportance, EventStatus, GateState,
)
from graxia.packages.quant_os.news_events.event_store import EventStore
from graxia.packages.quant_os.news_events.event_risk_gate import EventRiskGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_id="EVT-001",
    currency="USD",
    importance=EventImportance.HIGH,
    status=EventStatus.SCHEDULED,
    scheduled_at_utc=None,
    available_to_strategy_at_utc=None,
    actual=None,
    **kwargs,
):
    now = datetime.now(timezone.utc)
    sched = scheduled_at_utc or now
    avail = available_to_strategy_at_utc or now - timedelta(minutes=1)
    defaults = dict(
        event_id=event_id,
        source_event_id=f"src-{event_id}",
        country="US",
        currency=currency,
        event_name=f"Test Event {event_id}",
        importance=importance,
        scheduled_at_utc=sched,
        actual=actual,
        forecast=100.0,
        previous=99.0,
        revised_previous=None,
        source="test",
        official_url="https://example.com",
        received_at_utc=now - timedelta(minutes=5),
        available_to_strategy_at_utc=avail,
        source_revision_id="rev1",
        status=status,
    )
    defaults.update(kwargs)
    return EconomicEvent(**defaults)


# ---------------------------------------------------------------------------
# EventModels
# ---------------------------------------------------------------------------

class TestEconomicEvent:
    def test_creation(self):
        ev = _make_event()
        assert ev.event_id == "EVT-001"
        assert ev.importance == EventImportance.HIGH

    def test_payload_hash_deterministic(self):
        ev = _make_event()
        h1 = ev.payload_hash()
        h2 = ev.payload_hash()
        assert h1 == h2
        assert len(h1) == 64

    def test_payload_hash_changes_on_data(self):
        ev1 = _make_event(event_id="E1")
        ev2 = _make_event(event_id="E2")
        assert ev1.payload_hash() != ev2.payload_hash()

    def test_frozen(self):
        ev = _make_event()
        with pytest.raises(AttributeError):
            ev.event_id = "changed"


class TestEventImportance:
    def test_values(self):
        assert EventImportance.HIGH.value == "HIGH"
        assert EventImportance.MEDIUM.value == "MEDIUM"
        assert EventImportance.LOW.value == "LOW"


class TestEventStatus:
    def test_all_statuses_exist(self):
        expected = {"SCHEDULED", "RELEASED", "REVISED", "CANCELLED", "DELAYED", "UNKNOWN"}
        actual = {s.value for s in EventStatus}
        assert expected == actual


class TestGateState:
    def test_clear_and_block(self):
        assert GateState.CLEAR.value == "CLEAR"
        assert GateState.EVENT_BLOCK.value == "EVENT_BLOCK"


# ---------------------------------------------------------------------------
# EventStore
# ---------------------------------------------------------------------------

class TestEventStore:
    def test_add_and_query(self):
        store = EventStore()
        ev = _make_event(currency="USD")
        store.add_event(ev)
        results = store.query_at(as_of=datetime.now(timezone.utc), currency="USD")
        assert len(results) == 1

    def test_query_filters_by_currency(self):
        store = EventStore()
        store.add_event(_make_event(event_id="E1", currency="USD"))
        store.add_event(_make_event(event_id="E2", currency="EUR"))
        results = store.query_at(as_of=datetime.now(timezone.utc), currency="USD")
        assert len(results) == 1
        assert results[0].currency == "USD"

    def test_query_filters_future_events(self):
        store = EventStore()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        ev = _make_event(
            available_to_strategy_at_utc=future,
        )
        store.add_event(ev)
        results = store.query_at(as_of=datetime.now(timezone.utc))
        assert len(results) == 0

    def test_query_filters_by_importance(self):
        store = EventStore()
        store.add_event(_make_event(event_id="E1", importance=EventImportance.HIGH))
        store.add_event(_make_event(event_id="E2", importance=EventImportance.LOW))
        results = store.query_at(as_of=datetime.now(timezone.utc), min_importance="HIGH")
        assert len(results) == 1

    def test_add_event_replaces_older(self):
        store = EventStore()
        old = _make_event(event_id="E1", received_at_utc=datetime(2024, 1, 1, tzinfo=timezone.utc))
        store.add_event(old)
        new = _make_event(event_id="E1", received_at_utc=datetime(2024, 6, 1, tzinfo=timezone.utc))
        store.add_event(new)
        results = store.query_at(as_of=datetime.now(timezone.utc))
        assert len(results) == 1
        assert results[0].received_at_utc == datetime(2024, 6, 1, tzinfo=timezone.utc)

    def test_get_latest_status(self):
        store = EventStore()
        ev = _make_event(event_id="E1")
        store.add_event(ev)
        result = store.get_latest_status("E1", as_of=datetime.now(timezone.utc))
        assert result is not None
        assert result.event_id == "E1"

    def test_get_unknown_returns_none(self):
        store = EventStore()
        assert store.get_latest_status("UNKNOWN", as_of=datetime.now(timezone.utc)) is None


# ---------------------------------------------------------------------------
# EventRiskGate
# ---------------------------------------------------------------------------

class TestEventRiskGate:
    def test_clear_when_no_events(self):
        store = EventStore()
        gate = EventRiskGate(store)
        result = gate.evaluate(at=datetime.now(timezone.utc))
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True
        assert result.event_ids == []

    def test_blocks_during_high_impact_pre_event(self):
        store = EventStore()
        now = datetime.now(timezone.utc)
        # High-impact event 10 minutes from now → inside 30-min pre-block window
        ev = _make_event(
            importance=EventImportance.HIGH,
            scheduled_at_utc=now + timedelta(minutes=10),
        )
        store.add_event(ev)
        gate = EventRiskGate(store, pre_block_minutes=30, post_block_minutes=15)
        result = gate.evaluate(at=now)
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False
        assert len(result.event_ids) == 1

    def test_allows_low_impact_event(self):
        store = EventStore()
        now = datetime.now(timezone.utc)
        ev = _make_event(
            importance=EventImportance.LOW,
            scheduled_at_utc=now + timedelta(minutes=10),
        )
        store.add_event(ev)
        gate = EventRiskGate(store, pre_block_minutes=30, post_block_minutes=15)
        result = gate.evaluate(at=now)
        # LOW importance filtered by min_importance="HIGH" in query
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True

    def test_blocks_when_actual_missing_after_release(self):
        store = EventStore()
        now = datetime.now(timezone.utc)
        ev = _make_event(
            importance=EventImportance.HIGH,
            status=EventStatus.RELEASED,
            actual=None,
        )
        store.add_event(ev)
        gate = EventRiskGate(store)
        result = gate.evaluate(at=now)
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False

    def test_clear_after_event_window(self):
        store = EventStore()
        now = datetime.now(timezone.utc)
        # Event was 1 hour ago → outside 15-min post-block window
        ev = _make_event(
            importance=EventImportance.HIGH,
            scheduled_at_utc=now - timedelta(hours=1),
        )
        store.add_event(ev)
        gate = EventRiskGate(store, pre_block_minutes=30, post_block_minutes=15)
        result = gate.evaluate(at=now)
        assert result.state == GateState.CLEAR

    def test_evidence_hash_is_sha256(self):
        store = EventStore()
        gate = EventRiskGate(store)
        result = gate.evaluate(at=datetime.now(timezone.utc))
        assert len(result.evidence_hash) == 64

    def test_delayed_event_blocks(self):
        store = EventStore()
        now = datetime.now(timezone.utc)
        ev = _make_event(
            importance=EventImportance.HIGH,
            status=EventStatus.DELAYED,
            scheduled_at_utc=now + timedelta(minutes=5),
        )
        store.add_event(ev)
        gate = EventRiskGate(store, pre_block_minutes=30, post_block_minutes=15)
        result = gate.evaluate(at=now)
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False
