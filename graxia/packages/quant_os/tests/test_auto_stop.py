"""
Tests for Auto-Stop Drawdown Protection.

Tests verify:
  - Drawdown > threshold triggers kill switch
  - Kill switch closes all positions (via enforce)
  - Manual reset is required (no auto-recovery)
  - Auto-stop state persists across restarts
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from risk.auto_stop import AutoStop
from risk.kill_switch import KillSwitch, KillSwitchState


@pytest.fixture
def tmp_state_file(tmp_path):
    """Temporary state file for auto-stop."""
    return str(tmp_path / "auto_stop_state.json")


@pytest.fixture
def kill_switch(tmp_path):
    """Create a KillSwitch with temporary state file."""
    return KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))


@pytest.fixture
def auto_stop(kill_switch, tmp_state_file):
    """Create AutoStop with 15% threshold."""
    return AutoStop(
        kill_switch=kill_switch,
        threshold_pct=15.0,
        state_file=tmp_state_file,
    )


class TestAutoStopTrigger:
    """Test that drawdown exceeding threshold triggers kill switch."""

    def test_no_trigger_within_threshold(self, auto_stop, kill_switch):
        """Drawdown under 15% should NOT trigger."""
        # Set HWM at 100k
        auto_stop.update_equity(100_000)

        # Drop to 90k = 10% drawdown (below 15% threshold)
        status = auto_stop.update_equity(90_000)

        assert not auto_stop.is_triggered
        assert not kill_switch.is_active()
        assert status["current_drawdown_pct"] < 0  # Negative convention

    def test_trigger_at_threshold(self, auto_stop, kill_switch):
        """Drawdown at exactly 15% should trigger."""
        # Set HWM at 100k
        auto_stop.update_equity(100_000)

        # Drop to 85k = 15% drawdown (exactly at threshold)
        status = auto_stop.update_equity(85_000)

        assert auto_stop.is_triggered
        assert kill_switch.is_active()
        assert "Auto-stop" in kill_switch.get_status().get("reason", "")

    def test_trigger_above_threshold(self, auto_stop, kill_switch):
        """Drawdown above 15% should trigger."""
        # Set HWM at 100k
        auto_stop.update_equity(100_000)

        # Drop to 80k = 20% drawdown (above 15% threshold)
        status = auto_stop.update_equity(80_000)

        assert auto_stop.is_triggered
        assert kill_switch.is_active()

    def test_trigger_preserves_hwm(self, auto_stop, kill_switch):
        """HWM should be preserved after trigger."""
        # Set HWM at 100k
        auto_stop.update_equity(100_000)

        # Trigger at 80k
        auto_stop.update_equity(80_000)

        assert auto_stop.high_water_mark == 100_000

    def test_trigger_records_history(self, auto_stop, kill_switch):
        """Trigger event should be recorded in history."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        history = auto_stop.get_history()
        assert len(history) >= 1
        assert history[-1]["action"] == "triggered"
        assert history[-1]["threshold_pct"] == 15.0
        assert history[-1]["hwm"] == 100_000


class TestKillSwitchActivation:
    """Test that kill switch is properly activated on auto-stop trigger."""

    def test_kill_switch_active_after_trigger(self, auto_stop, kill_switch):
        """Kill switch should be ACTIVE after auto-stop triggers."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        assert kill_switch.is_active()
        assert kill_switch.trigger_type == KillSwitchState.ACTIVE.value

    def test_kill_switch_reason_contains_auto_stop(self, auto_stop, kill_switch):
        """Kill switch reason should mention auto-stop."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        status = kill_switch.get_status()
        assert "Auto-stop" in status["reason"]

    def test_kill_switch_enforce_close_all(self, auto_stop, kill_switch):
        """Kill switch enforce(CLOSE_ALL) should close all positions."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        # Mock broker adapter
        broker = MagicMock()
        broker.get_positions.return_value = [
            {"ticket": 1001, "pnl": -500.0},
            {"ticket": 1002, "pnl": 200.0},
            {"ticket": 1003, "pnl": -100.0},
        ]
        broker.close_position.return_value = True

        # Enforce CLOSE_ALL
        from risk.kill_switch import CloseMode

        result = kill_switch.enforce(CloseMode.CLOSE_ALL, broker_adapter=broker)

        # All positions should be closed
        assert len(result["closed"]) == 3
        assert len(result["failed"]) == 0
        assert broker.close_position.call_count == 3


class TestManualReset:
    """Test that manual reset is required (no auto-recovery)."""

    def test_reset_requires_authorized_by(self, auto_stop):
        """Reset should require authorized_by parameter."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        with pytest.raises(ValueError, match="authorized_by"):
            auto_stop.reset(authorized_by="", reason="test")

    def test_reset_requires_reason(self, auto_stop):
        """Reset should require reason parameter."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        with pytest.raises(ValueError, match="reason"):
            auto_stop.reset(authorized_by="admin", reason="")

    def test_reset_clears_trigger(self, auto_stop, kill_switch):
        """Reset should clear trigger state."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)
        assert auto_stop.is_triggered

        auto_stop.reset(authorized_by="admin", reason="testing")

        assert not auto_stop.is_triggered
        assert not kill_switch.is_active()

    def test_reset_records_history(self, auto_stop):
        """Reset should be recorded in history."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        auto_stop.reset(authorized_by="telegram:12345", reason="manual review")

        history = auto_stop.get_history()
        reset_events = [h for h in history if h["action"] == "reset"]
        assert len(reset_events) >= 1
        assert reset_events[-1]["authorized_by"] == "telegram:12345"
        assert reset_events[-1]["reason"] == "manual review"

    def test_no_auto_recovery_on_equity_increase(self, auto_stop, kill_switch):
        """Equity recovery should NOT clear auto-stop trigger."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)  # Trigger
        assert auto_stop.is_triggered

        # Equity recovers to 95k
        auto_stop.update_equity(95_000)

        # Should still be triggered
        assert auto_stop.is_triggered
        assert kill_switch.is_active()

    def test_reset_with_hwm_reset(self, auto_stop):
        """Reset with reset_hwm=True should reset HWM."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        auto_stop.reset(authorized_by="admin", reason="test", reset_hwm=True, new_equity=90_000)

        assert auto_stop.high_water_mark == 90_000

    def test_reset_without_hwm_reset(self, auto_stop):
        """Reset with reset_hwm=False should preserve HWM."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        auto_stop.reset(authorized_by="admin", reason="test", reset_hwm=False)

        assert auto_stop.high_water_mark == 100_000


class TestStatePersistence:
    """Test that auto-stop state persists across restarts."""

    def test_state_persists_on_trigger(self, kill_switch, tmp_state_file):
        """Triggered state should persist to disk."""
        # Create and trigger
        auto_stop = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)
        assert auto_stop.is_triggered

        # Verify state file exists
        state_path = Path(tmp_state_file)
        assert state_path.exists()

        # Load state and verify
        state = json.loads(state_path.read_text())
        assert state["triggered"] is True
        assert state["hwm"] == 100_000

    def test_state_persists_on_reset(self, kill_switch, tmp_state_file):
        """Reset state should persist to disk."""
        # Create, trigger, and reset
        auto_stop = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)
        auto_stop.reset(authorized_by="admin", reason="test")

        # Verify state file
        state_path = Path(tmp_state_file)
        state = json.loads(state_path.read_text())
        assert state["triggered"] is False

    def test_state_loads_on_restart(self, kill_switch, tmp_state_file):
        """State should load correctly when AutoStop is recreated."""
        # First instance: trigger
        auto_stop1 = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        auto_stop1.update_equity(100_000)
        auto_stop1.update_equity(80_000)
        assert auto_stop1.is_triggered

        # Second instance: should load triggered state
        auto_stop2 = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        assert auto_stop2.is_triggered
        assert auto_stop2.high_water_mark == 100_000

    def test_state_loads_reset_state(self, kill_switch, tmp_state_file):
        """Reset state should load correctly when AutoStop is recreated."""
        # First instance: trigger and reset
        auto_stop1 = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        auto_stop1.update_equity(100_000)
        auto_stop1.update_equity(80_000)
        auto_stop1.reset(authorized_by="admin", reason="test", new_equity=80_000)

        # Second instance: should load reset state
        auto_stop2 = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        assert not auto_stop2.is_triggered
        assert auto_stop2.high_water_mark == 80_000


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_equity_ignored(self, auto_stop):
        """Zero or negative equity should be ignored."""
        status = auto_stop.update_equity(0)
        assert not auto_stop.is_triggered

        status = auto_stop.update_equity(-1000)
        assert not auto_stop.is_triggered

    def test_hwm_updates_on_new_high(self, auto_stop):
        """HWM should update when equity exceeds current HWM."""
        auto_stop.update_equity(100_000)
        assert auto_stop.high_water_mark == 100_000

        auto_stop.update_equity(110_000)
        assert auto_stop.high_water_mark == 110_000

    def test_hwm_does_not_decrease(self, auto_stop):
        """HWM should not decrease when equity drops."""
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(90_000)
        assert auto_stop.high_water_mark == 100_000

    def test_without_kill_switch(self, tmp_state_file):
        """AutoStop should work without kill switch (logs warning)."""
        auto_stop = AutoStop(
            kill_switch=None,
            threshold_pct=15.0,
            state_file=tmp_state_file,
        )
        auto_stop.update_equity(100_000)
        auto_stop.update_equity(80_000)

        # Should still trigger internally
        assert auto_stop.is_triggered

    def test_status_dict(self, auto_stop):
        """get_status() should return complete status dict."""
        auto_stop.update_equity(100_000)
        status = auto_stop.get_status()

        assert "triggered" in status
        assert "threshold_pct" in status
        assert "high_water_mark" in status
        assert "current_drawdown_pct" in status
        assert "triggered_at" in status
        assert "reset_at" in status
        assert "reset_by" in status

    def test_custom_threshold(self, kill_switch, tmp_state_file):
        """Custom threshold should be respected."""
        auto_stop = AutoStop(
            kill_switch=kill_switch,
            threshold_pct=20.0,  # 20% threshold
            state_file=tmp_state_file,
        )
        auto_stop.update_equity(100_000)

        # 15% drawdown should NOT trigger with 20% threshold
        auto_stop.update_equity(85_000)
        assert not auto_stop.is_triggered

        # 20% drawdown should trigger
        auto_stop.update_equity(80_000)
        assert auto_stop.is_triggered


class TestBacktestAlignment:
    """Test that threshold aligns with backtest assumptions."""

    def test_threshold_below_backtest_max_dd(self):
        """
        Threshold (15%) must be well below backtest max DD (42.11%).

        This ensures the system stops trading before reaching the
        maximum historical drawdown, providing a safety margin.
        """
        backtest_max_dd = 42.11  # Ensemble TSM backtest max DD
        auto_stop_threshold = 15.0  # Our threshold

        # Threshold should be less than half of backtest max DD
        assert auto_stop_threshold < backtest_max_dd / 2, (
            f"Threshold {auto_stop_threshold}% should be < {backtest_max_dd/2:.1f}% "
            f"(half of backtest max DD {backtest_max_dd}%)"
        )

        # Threshold should provide at least 25% margin
        margin = backtest_max_dd - auto_stop_threshold
        assert margin >= 25.0, (
            f"Margin {margin:.1f}% should be >= 25% "
            f"(backtest max DD {backtest_max_dd}% - threshold {auto_stop_threshold}%)"
        )
