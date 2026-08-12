"""Pipeline Health Monitor — alerts when pipeline stops working."""

from __future__ import annotations

import time

import structlog

logger = structlog.get_logger(__name__)


class HealthMonitor:
    def __init__(self, stale_threshold_seconds: int = 600):
        self._last_success = time.time()
        self._threshold = stale_threshold_seconds
        self._consecutive_failures = 0

    def record_success(self):
        self._last_success = time.time()
        self._consecutive_failures = 0

    def record_failure(self):
        self._consecutive_failures += 1

    def is_stale(self) -> bool:
        return (time.time() - self._last_success) > self._threshold

    def get_status(self) -> dict:
        age = time.time() - self._last_success
        return {
            "healthy": not self.is_stale(),
            "last_success_age_seconds": round(age),
            "consecutive_failures": self._consecutive_failures,
            "threshold_seconds": self._threshold,
        }
