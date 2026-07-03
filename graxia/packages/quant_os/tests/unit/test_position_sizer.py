"""Unit tests for the real position sizing modules.

Imports from risk.position_sizer — no inline class definitions.
Tests standalone kelly_fraction() and TradeStatsTracker (config-free).
"""

import pytest

from graxia.packages.quant_os.risk.position_sizer import (
    TradeStatsTracker,
    kelly_fraction,
)

# ── Standalone kelly_fraction() ────────────────────────────────────────


class TestKellyFraction:
    def test_high_edge(self):
        result = kelly_fraction(win_rate=0.8, avg_win=3.0, avg_loss=1.0)
        assert result > 0.0
        assert result <= 0.25  # default fraction cap

    def test_negative_edge_returns_zero(self):
        result = kelly_fraction(win_rate=0.3, avg_win=1.0, avg_loss=1.0)
        assert result == 0.0

    def test_custom_fraction(self):
        full = kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0, fraction=1.0)
        half = kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0, fraction=0.5)
        assert full == pytest.approx(half * 2, abs=1e-6)

    def test_zero_avg_loss_returns_zero(self):
        result = kelly_fraction(win_rate=0.6, avg_win=1.0, avg_loss=0.0)
        assert result == 0.0

    def test_fifty_fifty_with_positive_edge(self):
        result = kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0, fraction=1.0)
        # Full Kelly: b=2, p=0.6, q=0.4 → (2*0.6 - 0.4)/2 = 0.4
        assert result == pytest.approx(0.4, abs=0.01)

    def test_breakeven_returns_zero(self):
        result = kelly_fraction(win_rate=0.5, avg_win=1.0, avg_loss=1.0)
        assert result == 0.0


# ── TradeStatsTracker ──────────────────────────────────────────────────


class TestTradeStatsTracker:
    def test_empty_tracker_has_defaults(self):
        tracker = TradeStatsTracker()
        assert tracker.win_rate == 0.5
        assert tracker.trade_count == 0

    def test_records_wins_and_losses(self):
        tracker = TradeStatsTracker()
        tracker.record(10.0)
        tracker.record(-5.0)
        tracker.record(8.0)
        assert tracker.trade_count == 3
        assert tracker.win_rate == pytest.approx(2 / 3)
        assert tracker.avg_win == pytest.approx(9.0)
        assert tracker.avg_loss == pytest.approx(5.0)

    def test_sliding_window(self):
        tracker = TradeStatsTracker(window=3)
        for _ in range(10):
            tracker.record(1.0)
        assert tracker.trade_count == 3  # window limits to 3

    def test_profit_factor(self):
        tracker = TradeStatsTracker()
        tracker.record(10.0)
        tracker.record(10.0)
        tracker.record(-5.0)
        assert tracker.profit_factor == pytest.approx(20.0 / 5.0)

    def test_profit_factor_all_wins(self):
        tracker = TradeStatsTracker()
        tracker.record(10.0)
        tracker.record(5.0)
        assert tracker.profit_factor == float("inf")

    def test_get_stats(self):
        tracker = TradeStatsTracker()
        tracker.record(10.0)
        stats = tracker.get_stats()
        assert "win_rate" in stats
        assert "avg_win" in stats
        assert "avg_loss" in stats
        assert "trade_count" in stats
        assert "profit_factor" in stats
