"""Phase BE-P2 integration tests — broker-aligned tick capture."""
import tempfile
from graxia.packages.quant_os.tick.tick_schema import TickRecord
from graxia.packages.quant_os.tick.tick_storage import TickStorage
from graxia.packages.quant_os.tick.data_quality import DataQualityChecker
from graxia.packages.quant_os.tick.feed_health import FeedHealthMonitor
from graxia.packages.quant_os.tick.tick_metrics import TickMetrics


def test_tick_record_full_lifecycle():
    tick = TickRecord(
        bid=2350.50, ask=2350.80, symbol="XAUUSD",
        source_timestamp_utc="2026-06-22T10:00:00", source_time_msc=1719052800000
    )
    tick.compute_spread()
    tick.compute_hashes()
    ok, issues = tick.validate()
    assert ok
    assert tick.spread_price == 0.30
    assert tick.raw_payload_hash


def test_storage_partition_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        tick_data = {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD", "source_timestamp_utc": "2026-06-22T10:00:00"}
        storage.store_tick(tick_data, "mt5", "MetaQuotes-Demo", "XAUUSD")
        storage.write_manifest("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22", 1)
        ok, msg = storage.verify_partition("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22")
        assert ok
        ticks = storage.read_ticks("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22")
        assert len(ticks) == 1


def test_quality_check_full():
    checker = DataQualityChecker()
    good = {"bid": 2350.50, "ask": 2350.80, "tick_id": 1, "source_time_msc": 1000, "ingest_sequence": 1}
    bad = {"bid": -1, "ask": 2350.80, "tick_id": 2, "source_time_msc": 2000, "ingest_sequence": 2}
    assert len(checker.check_tick(good)) == 0
    assert len(checker.check_tick(bad)) > 0


def test_feed_health_lifecycle():
    monitor = FeedHealthMonitor(stale_threshold_ms=100)
    monitor.start_session()
    monitor.record_tick(1000)
    assert not monitor.is_stale()
    state = monitor.get_state()
    assert state["tick_count"] == 1


def test_metrics_lifecycle():
    metrics = TickMetrics()
    metrics.start_session()
    for i in range(10):
        metrics.record_tick(0.30 + i * 0.01, 1000 + i, 0)
    summary = metrics.get_summary()
    assert summary["total_ticks"] == 10
    assert summary["spread"]["max"] > 0
