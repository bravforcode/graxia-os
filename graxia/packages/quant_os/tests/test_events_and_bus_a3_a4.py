"""Tests for A3: Event types + A4: Event bus"""

import pytest

from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import (
    BarEvent,
    Event,
    KillSwitchEvent,
    SignalEvent,
)

# ── A3 Tests: Event Types ────────────────────────────────────────


class TestEventBase:
    def test_event_frozen(self):
        e = Event()
        with pytest.raises(AttributeError):
            e.source = "x"

    def test_event_to_dict(self):
        e = Event(source="test")
        d = e.to_dict()
        assert "event_id" in d
        assert "timestamp" in d
        assert d["source"] == "test"
        assert d["event_type"] == "Event"

    def test_event_unique_ids(self):
        e1 = Event()
        e2 = Event()
        assert e1.event_id != e2.event_id


class TestBarEvent:
    def test_bar_event_fields(self):
        bar = BarEvent(symbol="XAUUSD", close=3340.0, volume=100)
        assert bar.symbol == "XAUUSD"
        assert bar.close == 3340.0
        assert bar.volume == 100

    def test_bar_event_to_dict(self):
        bar = BarEvent(symbol="EURUSD", close=1.1)
        d = bar.to_dict()
        assert d["event_type"] == "BarEvent"
        assert d["symbol"] == "EURUSD"
        assert d["close"] == 1.1


class TestSignalEvent:
    def test_signal_event_defaults(self):
        sig = SignalEvent()
        assert sig.signal_type == "NO_TRADE"
        assert sig.confidence == 0.0


class TestKillSwitchEvent:
    def test_kill_switch_fields(self):
        ks = KillSwitchEvent(trigger="DAILY_LOSS", reason="exceeded 5%")
        assert ks.trigger == "DAILY_LOSS"
        assert ks.severity == "P0"


# ── A4 Tests: Event Bus ──────────────────────────────────────────


class TestEventBus:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))
        bus.publish(BarEvent(symbol="XAUUSD"))
        assert len(received) == 1
        assert received[0].symbol == "XAUUSD"

    def test_multiple_subscribers(self):
        bus = EventBus()
        r1, r2 = [], []
        bus.subscribe(BarEvent, lambda e: r1.append(e))
        bus.subscribe(BarEvent, lambda e: r2.append(e))
        bus.publish(BarEvent(symbol="XAUUSD"))
        assert len(r1) == 1
        assert len(r2) == 1

    def test_type_filtering(self):
        bus = EventBus()
        bars, signals = [], []
        bus.subscribe(BarEvent, lambda e: bars.append(e))
        bus.subscribe(SignalEvent, lambda e: signals.append(e))
        bus.publish(BarEvent(symbol="XAUUSD"))
        bus.publish(SignalEvent(symbol="XAUUSD"))
        assert len(bars) == 1
        assert len(signals) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        handler = lambda e: received.append(e)
        bus.subscribe(BarEvent, handler)
        bus.publish(BarEvent())
        assert len(received) == 1
        removed = bus.unsubscribe(BarEvent, handler)
        assert removed is True
        bus.publish(BarEvent())
        assert len(received) == 1  # no new event

    def test_handler_exception_isolation(self):
        bus = EventBus()
        good_received = []

        def bad_handler(e):
            raise ValueError("boom")

        def good_handler(e):
            good_received.append(e)

        bus.subscribe(BarEvent, bad_handler)
        bus.subscribe(BarEvent, good_handler)
        bus.publish(BarEvent())
        assert len(good_received) == 1
        assert bus.handler_errors == 1

    def test_publish_count(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.publish(BarEvent())
        bus.publish(BarEvent())
        bus.publish(SignalEvent())
        assert bus.published_count == 3

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(SignalEvent, lambda e: None)
        assert bus.subscriber_count(BarEvent) == 2
        assert bus.subscriber_count(SignalEvent) == 1
        assert bus.subscriber_count() == 3

    def test_clear(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.clear()
        assert bus.subscriber_count() == 0

    def test_base_type_inheritance(self):
        """Handlers for Event base class receive all event types"""
        bus = EventBus()
        received = []
        bus.subscribe(Event, lambda e: received.append(e))
        bus.publish(BarEvent())
        bus.publish(SignalEvent())
        assert len(received) == 2
