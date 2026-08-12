"""Tests for tick analytics."""
import tempfile
from pathlib import Path
from graxia.packages.quant_os.tick.tick_analytics import TickAnalytics


def test_analytics_creates():
    analytics = TickAnalytics()
    assert analytics is not None


def test_spread_stats_empty():
    analytics = TickAnalytics()
    stats = analytics.query_spread_stats([])
    assert stats["count"] == 0


def test_spread_stats():
    analytics = TickAnalytics()
    # Varying spreads so p50 < max
    ticks = [
        {"bid": 100.0, "ask": 100.1 + (i * 0.01)}
        for i in range(100)
    ]
    stats = analytics.query_spread_stats(ticks)
    assert stats["count"] == 100
    assert stats["max"] > stats["p50"]


def test_export_parquet_fallback():
    analytics = TickAnalytics()
    ticks = [{"bid": 100.0, "ask": 100.3, "symbol": "XAUUSD"}]
    with tempfile.TemporaryDirectory() as tmpdir:
        out = str(Path(tmpdir) / "test.parquet")
        ok = analytics.export_parquet(ticks, out)
        assert ok


def test_duckdb_connect_fallback():
    analytics = TickAnalytics()
    result = analytics.connect()
    analytics.close()
    assert isinstance(result, bool)
