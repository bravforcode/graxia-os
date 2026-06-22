"""Tests for tick metrics."""
from graxia.packages.quant_os.tick.tick_metrics import TickMetrics


def test_metrics_creates():
    m = TickMetrics()
    assert m.get_summary()["total_ticks"] == 0


def test_metrics_records_tick():
    m = TickMetrics()
    m.start_session()
    m.record_tick(0.30, 1000000, 1000000000000)
    s = m.get_summary()
    assert s["total_ticks"] == 1
    assert s["spread"]["p50"] == 0.30


def test_metrics_spread_stats():
    m = TickMetrics()
    for i in range(100):
        m.record_tick(0.1 + i * 0.01, 1000 + i, 0)
    stats = m.get_spread_stats()
    assert stats["max"] > stats["p50"]


def test_metrics_incidents():
    m = TickMetrics()
    m.record_stale()
    m.record_duplicate()
    m.record_gap()
    s = m.get_summary()
    assert s["stale_count"] == 1
    assert s["duplicate_count"] == 1
    assert s["gap_count"] == 1
