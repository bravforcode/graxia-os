"""Tests for event gate."""
from datetime import datetime, timezone
from graxia.packages.quant_os.events.event_gate import EventGate, EventRecord, GateState


def test_gate_starts_clear():
    gate = EventGate()
    assert gate.get_state() == GateState.CLEAR


def test_gate_blocks_pre_event():
    gate = EventGate(pre_block_minutes=60)
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    event = EventRecord(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:30:00+00:00",
    )
    state = gate.evaluate(now, [event])
    assert state == GateState.PRE_EVENT_BLOCK
    assert gate.is_blocking()


def test_gate_clear_after_event():
    gate = EventGate(post_block_minutes=5)
    now = datetime(2026, 6, 22, 12, 30, tzinfo=timezone.utc)
    event = EventRecord(
        event_id="EVT001", event_name="NFP", importance="HIGH",
        scheduled_at_utc="2026-06-22T12:00:00+00:00",
        published_at_utc="2026-06-22T12:00:00+00:00",
    )
    state = gate.evaluate(now, [event])
    assert state == GateState.CLEAR
    assert not gate.is_blocking()


def test_gate_clear_no_events():
    gate = EventGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    state = gate.evaluate(now, [])
    assert state == GateState.CLEAR
    assert not gate.is_blocking()


def test_gate_ignores_low_importance():
    gate = EventGate(pre_block_minutes=60)
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    event = EventRecord(
        event_id="EVT001", event_name="Minor", importance="LOW",
        scheduled_at_utc="2026-06-22T12:10:00+00:00",
    )
    state = gate.evaluate(now, [event])
    assert state == GateState.CLEAR
