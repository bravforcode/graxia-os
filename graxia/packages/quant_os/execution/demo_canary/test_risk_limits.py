"""Tests for risk limit tracker + trading config."""
import os, sys
from datetime import date
from unittest.mock import patch

_test_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _test_root not in sys.path:
    sys.path.insert(0, _test_root)

from config.trading_config import TradingMode, get_trading_mode, RiskLimits  # noqa: E402
from execution.demo_canary.risk_limits import DailyRiskTracker  # noqa: E402


class TestTradingConfig:
    def test_default_mode_is_demo(self):
        mode = get_trading_mode()
        assert mode == TradingMode.DEMO

    def test_env_overrides_mode(self):
        with patch.dict(os.environ, {"TRADING_MODE": "LIVE"}, clear=False):
            assert get_trading_mode() == TradingMode.LIVE

    def test_invalid_env_falls_back_to_demo(self):
        with patch.dict(os.environ, {"TRADING_MODE": "BOGUS"}, clear=False):
            assert get_trading_mode() == TradingMode.DEMO

    def test_risk_limits_defaults(self):
        limits = RiskLimits()
        assert limits.max_daily_loss_pct == 2.0
        assert limits.max_position_size_pct == 5.0
        assert limits.max_consecutive_losses == 3
        assert limits.max_daily_trades == 10

    def test_risk_limits_env(self):
        with patch.dict(os.environ, {
            "RISK_MAX_DAILY_LOSS_PCT": "5.0",
            "RISK_MAX_CONSECUTIVE_LOSSES": "5",
        }, clear=False):
            limits = RiskLimits()
            assert limits.max_daily_loss_pct == 5.0
            assert limits.max_consecutive_losses == 5


class TestDailyRiskTracker:
    def test_starts_clean(self):
        tracker = DailyRiskTracker()
        assert tracker.daily_pnl == 0.0
        assert tracker.trade_count == 0
        assert tracker.consecutive_losses == 0

    def test_records_winning_trade(self):
        tracker = DailyRiskTracker()
        tracker.record_trade(50.0, equity=10000)
        assert tracker.daily_pnl == 50.0
        assert tracker.trade_count == 1
        assert tracker.consecutive_losses == 0

    def test_records_losing_trade(self):
        tracker = DailyRiskTracker()
        tracker.record_trade(-30.0, equity=10000)
        assert tracker.daily_pnl == -30.0
        assert tracker.consecutive_losses == 1

    def test_consecutive_losses_reset_on_win(self):
        tracker = DailyRiskTracker()
        tracker.record_trade(-10.0)
        tracker.record_trade(-20.0)
        assert tracker.consecutive_losses == 2
        tracker.record_trade(5.0)
        assert tracker.consecutive_losses == 0

    def test_no_violations_when_under_limits(self):
        tracker = DailyRiskTracker()
        violations = tracker.check_limits(equity=10000)
        assert violations == []

    def test_daily_loss_limit(self):
        tracker = DailyRiskTracker()
        tracker.record_trade(-300.0, equity=1000)
        violations = tracker.check_limits(equity=1000)
        assert any("Daily loss" in v for v in violations)

    def test_trade_count_limit(self):
        limits = RiskLimits()
        limits.max_daily_trades = 2
        tracker = DailyRiskTracker(limits=limits)
        tracker.record_trade(10.0)
        tracker.record_trade(10.0)
        violations = tracker.check_limits(equity=1000)
        assert any("Trade count" in v for v in violations)

    def test_consecutive_loss_limit(self):
        limits = RiskLimits()
        limits.max_consecutive_losses = 2
        tracker = DailyRiskTracker(limits=limits)
        tracker.record_trade(-10.0)
        tracker.record_trade(-10.0)
        violations = tracker.check_limits(equity=1000)
        assert any("Consecutive losses" in v for v in violations)

    def test_drawdown_limit(self):
        limits = RiskLimits()
        limits.max_drawdown_pct = 5.0
        tracker = DailyRiskTracker(limits=limits)
        tracker.record_trade(0.0, equity=1000)
        violations = tracker.check_limits(equity=940)
        assert any("Drawdown" in v for v in violations)

    def test_reset_on_new_day(self):
        tracker = DailyRiskTracker()
        tracker.record_trade(-999.0)
        # Simulate new day by forcing today to past
        tracker._today = date(2020, 1, 1)
        tracker.reset_if_new_day()
        assert tracker.daily_pnl == 0.0
        assert tracker.trade_count == 0
        assert tracker.consecutive_losses == 0
