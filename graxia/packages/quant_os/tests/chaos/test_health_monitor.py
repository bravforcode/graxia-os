"""Tests for HealthMonitor."""

import time


from graxia.packages.quant_os.core.agents.health_monitor import HealthMonitor


class TestHealthMonitor:
    def test_record_success_resets_timer(self):
        m = HealthMonitor(stale_threshold_seconds=60)
        m.record_failure()
        m.record_failure()
        assert m._consecutive_failures == 2

        m.record_success()
        assert m._consecutive_failures == 0
        assert not m.is_stale()

    def test_is_stale_returns_true_after_threshold(self):
        m = HealthMonitor(stale_threshold_seconds=1)
        assert not m.is_stale()

        m._last_success = time.time() - 2
        assert m.is_stale()

    def test_consecutive_failures_counts(self):
        m = HealthMonitor()
        assert m._consecutive_failures == 0
        m.record_failure()
        m.record_failure()
        m.record_failure()
        assert m._consecutive_failures == 3

        m.record_success()
        assert m._consecutive_failures == 0

    def test_get_status_format(self):
        m = HealthMonitor(stale_threshold_seconds=300)
        status = m.get_status()
        assert set(status.keys()) == {
            "healthy",
            "last_success_age_seconds",
            "consecutive_failures",
            "threshold_seconds",
        }
        assert isinstance(status["healthy"], bool)
        assert isinstance(status["last_success_age_seconds"], int)
        assert isinstance(status["consecutive_failures"], int)
        assert status["threshold_seconds"] == 300

    def test_fresh_monitor_is_healthy(self):
        m = HealthMonitor(stale_threshold_seconds=600)
        assert not m.is_stale()
        assert m.get_status()["healthy"] is True
