"""
PipelineMetrics Tests
=====================
Verifies metrics tracking and to_dict format.

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_metrics.py -v
"""

from __future__ import annotations

import logging

from graxia.packages.quant_os.core.metrics import PipelineMetrics


class TestPipelineMetrics:
    def test_defaults(self):
        m = PipelineMetrics()
        assert m.headlines_processed == 0
        assert m.signals_generated == 0
        assert m.orders_placed == 0
        assert m.signals_blocked == 0
        assert m.regime_changes == 0
        assert m.current_regime == "NORMAL"
        assert m.current_position_mult == 1.0
        assert m.last_update is not None

    def test_to_dict_all_keys(self):
        d = PipelineMetrics().to_dict()
        expected = {
            "headlines_processed",
            "signals_generated",
            "orders_placed",
            "signals_blocked",
            "regime_changes",
            "current_regime",
            "current_position_mult",
            "last_update",
        }
        assert set(d.keys()) == expected

    def test_to_dict_datetime_serialized(self):
        d = PipelineMetrics().to_dict()
        assert isinstance(d["last_update"], str)
        assert "T" in d["last_update"]

    def test_to_dict_numeric_values(self):
        m = PipelineMetrics(headlines_processed=42, signals_generated=3)
        d = m.to_dict()
        assert d["headlines_processed"] == 42
        assert d["signals_generated"] == 3

    def test_to_dict_regime_and_mult(self):
        m = PipelineMetrics(current_regime="CRISIS", current_position_mult=0.25)
        d = m.to_dict()
        assert d["current_regime"] == "CRISIS"
        assert d["current_position_mult"] == 0.25

    def test_log_summary_calls_logger(self, caplog):
        m = PipelineMetrics(headlines_processed=5, current_regime="HIGH_UNCERTAINTY")
        logger = logging.getLogger("test.metrics")
        with caplog.at_level(logging.INFO, logger="test.metrics"):
            m.log_summary(logger)
        assert "pipeline.metrics" in caplog.text
        assert "5" in caplog.text
        assert "HIGH_UNCERTAINTY" in caplog.text

    def test_increment_counters(self):
        m = PipelineMetrics()
        m.headlines_processed += 10
        m.signals_generated += 3
        m.orders_placed += 1
        m.signals_blocked += 2
        m.regime_changes += 1
        d = m.to_dict()
        assert d["headlines_processed"] == 10
        assert d["signals_generated"] == 3
        assert d["orders_placed"] == 1
        assert d["signals_blocked"] == 2
        assert d["regime_changes"] == 1
