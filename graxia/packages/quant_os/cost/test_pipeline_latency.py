"""Tests for pipeline latency tracker."""
import time
from graxia.packages.quant_os.cost.pipeline_latency import PipelineLatencyTracker


def test_tracker_creates():
    tracker = PipelineLatencyTracker()
    assert tracker.get_stats()["count"] == 0


def test_tracker_records_sample():
    tracker = PipelineLatencyTracker()
    tracker.on_tick_received()
    time.sleep(0.001)
    tracker.on_signal_finalized()
    time.sleep(0.001)
    tracker.on_order_persisted()
    stats = tracker.get_stats()
    assert stats["count"] == 1
    assert stats["avg_total_ms"] >= 0


def test_tracker_multiple_samples():
    tracker = PipelineLatencyTracker()
    for _ in range(5):
        tracker.on_tick_received()
        tracker.on_signal_finalized()
        tracker.on_order_persisted()
    stats = tracker.get_stats()
    assert stats["count"] == 5


def test_tracker_incomplete_sample():
    tracker = PipelineLatencyTracker()
    tracker.on_tick_received()
    # Never finalized or persisted
    tracker.on_order_persisted()
    assert tracker.get_stats()["count"] == 0
