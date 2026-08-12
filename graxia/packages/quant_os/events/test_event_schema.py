"""Tests for event schema and provider."""
from graxia.packages.quant_os.events.event_schema import PointInTimeEvent
from graxia.packages.quant_os.events.event_provider import EventProvider


def test_event_creation():
    event = PointInTimeEvent(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:30:00Z",
    )
    ok, issues = event.validate()
    assert ok


def test_event_hash():
    event = PointInTimeEvent(event_id="EVT001", event_name="NFP")
    event.compute_hash()
    assert event.payload_hash


def test_event_validation_fails():
    event = PointInTimeEvent()
    ok, issues = event.validate()
    assert not ok
    assert any("event_id" in i for i in issues)


def test_provider_creates_event():
    provider = EventProvider(name="fred", version="1.0", tier=3)
    event = provider.create_event("CPI", "HIGH", "2026-07-15T08:30:00Z", "US", "USD")
    assert event.event_name == "CPI"
    assert event.provider_version == "1.0"
    assert event.payload_hash


def test_provider_updates_actual():
    provider = EventProvider(name="fred", version="1.0", tier=3)
    event = provider.create_event("CPI", "HIGH", "2026-07-15T08:30:00Z")
    updated = provider.update_actual(event, "3.2%", "2026-07-15T08:30:05Z")
    assert updated.actual == "3.2%"
    assert updated.official_confirmation is False  # tier 3


def test_provider_tier1_official():
    provider = EventProvider(name="federal_reserve", version="1.0", tier=1)
    event = provider.create_event("FOMC", "HIGH", "2026-07-15T14:00:00Z")
    updated = provider.update_actual(event, "5.25%", "2026-07-15T14:00:05Z")
    assert updated.official_confirmation is True
