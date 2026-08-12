"""Tests for AutonomousEngine safety guards."""

from __future__ import annotations

import time


from graxia.packages.quant_os.core.agents.autonomous_engine import (
    AutonomousEngine,
    EngineState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine(**kwargs) -> AutonomousEngine:
    """Create an engine with optional attribute overrides."""
    e = AutonomousEngine()
    for k, v in kwargs.items():
        setattr(e, k, v)
    return e


def _good_kwargs(**overrides) -> dict:
    """Default kwargs where all guards pass."""
    defaults = dict(
        symbol="XAUUSD",
        signal="BUY",
        confidence=0.85,
        regime_label="NORMAL",
        is_news_blocked=False,
        session_active=True,
        correlation_adj=1.0,
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestEngineState:
    def test_initial_state(self):
        e = AutonomousEngine()
        assert e._state == EngineState.IDLE
        assert e._kill_switch is False
        assert e._daily_pnl == 0.0
        assert e._weekly_pnl == 0.0
        assert e._open_positions == 0

    def test_emergency_stop_sets_killed(self):
        e = AutonomousEngine()
        e.emergency_stop()
        assert e._state == EngineState.KILLED
        assert e._kill_switch is True

    def test_resume_clears_kill_switch(self):
        e = AutonomousEngine()
        e.emergency_stop()
        assert e._state == EngineState.KILLED
        e.resume()
        assert e._kill_switch is False
        assert e._state == EngineState.IDLE

    def test_resume_without_stop(self):
        e = AutonomousEngine()
        e.resume()
        assert e._kill_switch is False
        assert e._state == EngineState.IDLE


# ---------------------------------------------------------------------------
# Guard: Kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_kill_switch_rejects_trade(self):
        e = AutonomousEngine()
        e.emergency_stop()
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert "kill_switch" in d.guards_checked
        assert "kill_switch" not in d.guards_passed
        assert "Kill switch" in d.reason


# ---------------------------------------------------------------------------
# Guard: Daily loss
# ---------------------------------------------------------------------------


class TestDailyLoss:
    def test_daily_loss_rejects_trade(self):
        e = AutonomousEngine()
        e._daily_pnl = -2.5
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert "daily_loss" in d.guards_checked
        assert "daily_loss" not in d.guards_passed
        assert "Daily loss" in d.reason
        assert e._state == EngineState.RISK_LOCKED

    def test_daily_loss_exact_boundary_not_triggered(self):
        e = AutonomousEngine()
        e._daily_pnl = -1.99
        d = e.evaluate(**_good_kwargs())
        assert d.action == "BUY"
        assert "daily_loss" in d.guards_passed

    def test_daily_loss_at_limit_rejected(self):
        e = AutonomousEngine()
        e._daily_pnl = -2.0
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"


# ---------------------------------------------------------------------------
# Guard: Weekly loss
# ---------------------------------------------------------------------------


class TestWeeklyLoss:
    def test_weekly_loss_rejects_trade(self):
        e = AutonomousEngine()
        e._weekly_pnl = -5.5
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert "weekly_loss" in d.guards_checked
        assert "weekly_loss" not in d.guards_passed
        assert "Weekly loss" in d.reason
        assert e._state == EngineState.RISK_LOCKED

    def test_weekly_loss_boundary_not_triggered(self):
        e = AutonomousEngine()
        e._weekly_pnl = -4.99
        d = e.evaluate(**_good_kwargs())
        assert d.action == "BUY"

    def test_weekly_loss_at_limit_rejected(self):
        e = AutonomousEngine()
        e._weekly_pnl = -5.0
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"


# ---------------------------------------------------------------------------
# Guard: Max positions
# ---------------------------------------------------------------------------


class TestMaxPositions:
    def test_max_positions_rejects_trade(self):
        e = AutonomousEngine()
        e._open_positions = 3
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert "max_positions" in d.guards_checked
        assert "max_positions" not in d.guards_passed

    def test_below_max_positions_accepted(self):
        e = AutonomousEngine()
        e._open_positions = 2
        d = e.evaluate(**_good_kwargs())
        assert d.action == "BUY"
        assert "max_positions" in d.guards_passed


# ---------------------------------------------------------------------------
# Guard: News blackout
# ---------------------------------------------------------------------------


class TestNewsBlackout:
    def test_news_blackout_rejects_trade(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(is_news_blocked=True))
        assert d.action == "HOLD"
        assert "news_blackout" in d.guards_checked
        assert "news_blackout" not in d.guards_passed
        assert "News blackout" in d.reason
        assert e._state == EngineState.PAUSED


# ---------------------------------------------------------------------------
# Guard: Session filter
# ---------------------------------------------------------------------------


class TestSessionFilter:
    def test_session_inactive_rejects_trade(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(session_active=False))
        assert d.action == "HOLD"
        assert "session_filter" in d.guards_checked
        assert "session_filter" not in d.guards_passed
        assert "Outside trading session" in d.reason
        assert e._state == EngineState.PAUSED


# ---------------------------------------------------------------------------
# Guard: Regime gate
# ---------------------------------------------------------------------------


class TestRegimeGate:
    def test_crisis_regime_rejects_trade(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(regime_label="CRISIS"))
        assert d.action == "HOLD"
        assert "regime_gate" in d.guards_checked
        assert "regime_gate" not in d.guards_passed
        assert "CRISIS" in d.reason

    def test_normal_regime_passes(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(regime_label="NORMAL"))
        assert d.action == "BUY"
        assert "regime_gate" in d.guards_passed


# ---------------------------------------------------------------------------
# Guard: Cooldown
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_cooldown_rejects_trade(self):
        e = AutonomousEngine()
        e._last_trade_time = time.time()  # just traded
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert "cooldown" in d.guards_checked
        assert "cooldown" not in d.guards_passed
        assert "Cooldown" in d.reason

    def test_cooldown_expired_accepted(self):
        e = AutonomousEngine()
        e._last_trade_time = time.time() - 301  # 5 min + 1s ago
        d = e.evaluate(**_good_kwargs())
        assert d.action == "BUY"
        assert "cooldown" in d.guards_passed


# ---------------------------------------------------------------------------
# Guard: Confidence
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_low_confidence_rejects_trade(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(confidence=0.3))
        assert d.action == "HOLD"
        assert "confidence" in d.guards_checked
        assert "confidence" not in d.guards_passed
        assert "Low confidence" in d.reason

    def test_boundary_confidence_rejects(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(confidence=0.59))
        assert d.action == "HOLD"

    def test_acceptable_confidence_passes(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(confidence=0.6))
        assert d.action == "BUY"
        assert "confidence" in d.guards_passed


# ---------------------------------------------------------------------------
# All guards pass
# ---------------------------------------------------------------------------


class TestAllGuardsPass:
    def test_trade_approved_when_all_guards_pass(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs())
        assert d.action == "BUY"
        assert d.symbol == "XAUUSD"
        assert d.confidence == 0.85
        assert d.position_size_pct == 1.0
        assert len(d.guards_passed) == 9
        assert len(d.guards_checked) == 9
        assert d.guards_checked == d.guards_passed

    def test_sell_signal_approved(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(signal="SELL"))
        assert d.action == "SELL"

    def test_trade_log_appended(self):
        e = AutonomousEngine()
        assert len(e._trade_log) == 0
        e.evaluate(**_good_kwargs())
        assert len(e._trade_log) == 1
        assert e._trade_log[0]["symbol"] == "XAUUSD"


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------


class TestPositionSizing:
    def test_high_uncertainty_reduces_size(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(regime_label="HIGH_UNCERTAINTY"))
        assert d.position_size_pct == 0.5

    def test_correlation_adjustment(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(correlation_adj=0.5))
        assert d.position_size_pct == 0.5

    def test_high_uncertainty_and_correlation(self):
        e = AutonomousEngine()
        d = e.evaluate(
            **_good_kwargs(regime_label="HIGH_UNCERTAINTY", correlation_adj=0.6)
        )
        # 1.0 * 0.5 * 0.6 = 0.3
        assert d.position_size_pct == 0.3

    def test_position_capped_at_max(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(correlation_adj=2.0))
        assert d.position_size_pct == 1.0

    def test_normal_regime_full_size(self):
        e = AutonomousEngine()
        d = e.evaluate(**_good_kwargs(regime_label="NORMAL"))
        assert d.position_size_pct == 1.0


# ---------------------------------------------------------------------------
# PnL tracking
# ---------------------------------------------------------------------------


class TestPnL:
    def test_record_pnl_accumulates(self):
        e = AutonomousEngine()
        e.record_pnl(0.5)
        assert e._daily_pnl == 0.5
        assert e._weekly_pnl == 0.5
        e.record_pnl(-0.3)
        assert e._daily_pnl == 0.2
        assert e._weekly_pnl == 0.2

    def test_record_pnl_triggers_daily_lock(self):
        e = AutonomousEngine()
        e.record_pnl(-2.1)
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"
        assert e._state == EngineState.RISK_LOCKED

    def test_record_pnl_triggers_weekly_lock(self):
        e = AutonomousEngine()
        e._daily_pnl = -1.0  # under daily limit
        e.record_pnl(-4.5)  # total weekly = -5.5
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------


class TestPositionTracking:
    def test_record_position_open_close(self):
        e = AutonomousEngine()
        assert e._open_positions == 0
        e.record_position_open()
        assert e._open_positions == 1
        e.record_position_open()
        assert e._open_positions == 2
        e.record_position_close()
        assert e._open_positions == 1

    def test_close_does_not_go_negative(self):
        e = AutonomousEngine()
        e.record_position_close()
        assert e._open_positions == 0

    def test_open_blocks_when_at_max(self):
        e = AutonomousEngine()
        e._open_positions = 3
        d = e.evaluate(**_good_kwargs())
        assert d.action == "HOLD"


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


class TestGetState:
    def test_get_state_returns_dict(self):
        e = AutonomousEngine()
        s = e.get_state()
        assert isinstance(s, dict)
        assert s["state"] == "idle"
        assert s["kill_switch"] is False
        assert s["daily_pnl"] == 0.0
        assert s["weekly_pnl"] == 0.0
        assert s["open_positions"] == 0
        assert s["trade_count"] == 0

    def test_get_state_reflects_trades(self):
        e = AutonomousEngine()
        e.evaluate(**_good_kwargs())
        s = e.get_state()
        assert s["trade_count"] == 1
        assert s["state"] == "trading"

    def test_get_state_after_kill(self):
        e = AutonomousEngine()
        e.emergency_stop()
        s = e.get_state()
        assert s["state"] == "killed"
        assert s["kill_switch"] is True


# ---------------------------------------------------------------------------
# Guard ordering (early reject short-circuits)
# ---------------------------------------------------------------------------


class TestGuardOrdering:
    def test_kill_switch_checked_first(self):
        e = AutonomousEngine()
        e.emergency_stop()
        e._daily_pnl = -10.0  # would also fail daily loss
        d = e.evaluate(**_good_kwargs())
        assert "kill_switch" in d.guards_checked
        assert "daily_loss" not in d.guards_checked

    def test_daily_loss_before_weekly_loss(self):
        e = AutonomousEngine()
        e._daily_pnl = -3.0
        e._weekly_pnl = -6.0
        d = e.evaluate(**_good_kwargs())
        assert "daily_loss" in d.guards_checked
        assert "daily_loss" not in d.guards_passed
        # weekly_loss not reached because daily_loss rejected first
        assert "weekly_loss" not in d.guards_checked
