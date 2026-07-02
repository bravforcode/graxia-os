"""Integration test for previously skipped items now implemented."""
from datetime import datetime, UTC
from graxia.packages.quant_os.tick.data_quality import DataQualityChecker
from graxia.packages.quant_os.tick.tick_analytics import TickAnalytics
from graxia.packages.quant_os.tick.tick_logger import TickLogger
from graxia.packages.quant_os.events.event_gate import EventGate, GateState, EventRecord
from graxia.packages.quant_os.events.event_metrics import EventMetrics


def test_stale_quality_rule():
    checker = DataQualityChecker(stale_threshold_ms=100)
    checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1000, "ingest_sequence": 1})
    checker._last_source_time_ms = 1000
    checker._last_sequence = 1
    incidents = checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 800, "ingest_sequence": 2})
    assert any(i.incident_type == "stale" for i in incidents)


def test_session_break_quality_rule():
    checker = DataQualityChecker()
    checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1000000, "ingest_sequence": 1})
    incidents = checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1360000, "ingest_sequence": 2})
    assert any(i.incident_type == "session_break" for i in incidents)


def test_parquet_export():
    import tempfile
    from pathlib import Path
    analytics = TickAnalytics()
    ticks = [{"bid": 100.0, "ask": 100.3, "symbol": "XAUUSD"}]
    tmp_dir = tempfile.mkdtemp()
    out = Path(tmp_dir) / "test.parquet"
    ok = analytics.export_parquet(ticks, str(out))
    assert ok
    # pyarrow writes .parquet, fallback writes .jsonl
    assert out.exists() or Path(str(out).replace(".parquet", ".jsonl")).exists()


def test_unknown_fail_closed():
    gate = EventGate()
    event = EventRecord(event_id="EVT001", event_name="", importance="HIGH",
                        scheduled_at_utc="2026-06-22T12:00:00+00:00")
    state = gate.evaluate_unknown([event])
    assert state == GateState.UNKNOWN_FAIL_CLOSED


def test_medium_importance():
    gate = EventGate()
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    event = EventRecord(
        event_id="EVT002", event_name="Retail Sales", importance="MEDIUM",
        scheduled_at_utc="2026-06-22T12:10:00+00:00",
    )
    state = gate.evaluate(now, [event])
    assert state == GateState.PRE_EVENT_BLOCK


def test_event_metrics():
    m = EventMetrics()
    m.record_event_received("NFP", "HIGH")
    m.record_block("NFP", "pre_event", 500)
    s = m.get_summary()
    assert s["events_blocked"] == 1


def test_tick_logger():
    logger = TickLogger()
    logger.log_tick_received("XAUUSD", 2350.50, 2350.80, 1000)
    logger.log_quality_incident("stale", 5, "age=5000ms")
    assert len(logger.get_entries()) == 2
