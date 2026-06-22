"""Tests for feed health monitor."""
import time
from graxia.packages.quant_os.tick.feed_health import FeedHealthMonitor


def test_monitor_creates():
    monitor = FeedHealthMonitor()
    assert monitor.get_tick_count() == 0


def test_monitor_records_tick():
    monitor = FeedHealthMonitor()
    monitor.start_session()
    monitor.record_tick(1000)
    assert monitor.get_tick_count() == 1
    assert monitor.get_watermark() == 1000


def test_monitor_staleness():
    monitor = FeedHealthMonitor(stale_threshold_ms=10)
    monitor.start_session()
    assert monitor.is_stale()  # no ticks yet
    monitor.record_tick(1000)
    assert not monitor.is_stale()  # just received
    time.sleep(0.02)  # 20ms > 10ms threshold
    assert monitor.is_stale()


def test_monitor_state():
    monitor = FeedHealthMonitor()
    monitor.start_session()
    monitor.record_tick(5000)
    state = monitor.get_state()
    assert state["watermark_ms"] == 5000
    assert state["tick_count"] == 1