"""
Safety Fix Tests — Kill Switch enforce() wiring and Circuit Breaker → Kill Switch.

Tests:
  TASK 1: _set_state() calls enforce() on ACTIVE transition
  TASK 1: Corrupted state value defaults to ACTIVE (fail-closed)
  TASK 2: record_trade() activates kill switch when threshold hit
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from risk.kill_switch import CloseMode, KillSwitch, KillSwitchState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_positions(n: int = 3) -> list[dict]:
    return [{"ticket": 1000 + i, "symbol": f"SYM{i}", "pnl": float(i - 1), "volume": 0.1} for i in range(n)]


def _mock_broker(positions: list[dict] | None = None) -> MagicMock:
    """Return a mock BrokerAdapterLike. Mutates shared list on close."""
    if positions is None:
        positions = _make_positions(3)
    broker = MagicMock()
    broker.get_positions.side_effect = lambda: list(positions)

    def _close(ticket: int) -> None:
        positions[:] = [p for p in positions if p["ticket"] != ticket]

    broker.close_position.side_effect = _close
    return broker


# ===========================================================================
# TASK 1: Kill Switch enforce() wiring
# ===========================================================================


class TestEnforceWiredIntoActivation:
    """_set_state() must call enforce() when transitioning to ACTIVE."""

    def test_activate_calls_enforce(self, tmp_path: Path):
        """activate() → _set_state(ACTIVE) → enforce() closes positions."""
        positions = _make_positions(3)
        broker = _mock_broker(positions)
        ks = KillSwitch(
            state_file=str(tmp_path / "ks.json"),
            broker_adapter=broker,
            close_mode=CloseMode.CLOSE_ALL,
        )

        # activate() should trigger enforce() internally
        ks.activate(reason="test", source="test")

        assert ks.is_active()
        assert broker.close_position.call_count == 3, "enforce() must close all 3 positions"

    def test_cmd_kill_all_calls_enforce(self, tmp_path: Path):
        """Telegram /kill_all must close positions via enforce()."""
        positions = _make_positions(2)
        broker = _mock_broker(positions)

        with patch.dict("os.environ", {"TELEGRAM_ALLOWED_USERS": "12345"}):
            ks = KillSwitch(
                state_file=str(tmp_path / "ks.json"),
                broker_adapter=broker,
                close_mode=CloseMode.CLOSE_ALL,
            )
            result = ks.handle_command("/kill_all", 12345)

        assert "KILL SWITCH" in result
        assert broker.close_position.call_count == 2

    def test_no_enforce_when_already_active(self, tmp_path: Path):
        """Transitioning ACTIVE→ACTIVE must NOT re-enforce (idempotent)."""
        positions = _make_positions(2)
        broker = _mock_broker(positions)
        ks = KillSwitch(
            state_file=str(tmp_path / "ks.json"),
            broker_adapter=broker,
        )

        # First activation: closes 2 positions
        ks.activate(reason="first", source="test")
        assert broker.close_position.call_count == 2

        # Reset mock counts
        broker.close_position.reset_mock()

        # Second activation: no positions left, enforce called but no-op
        ks.activate(reason="second", source="test")
        # enforce() is called but finds no positions → close_position not called
        assert broker.close_position.call_count == 0

    def test_no_enforce_on_deactivate(self, tmp_path: Path):
        """deactivate() must NOT call enforce()."""
        broker = _mock_broker(_make_positions(2))
        ks = KillSwitch(
            state_file=str(tmp_path / "ks.json"),
            broker_adapter=broker,
        )

        # Activate first (will enforce)
        ks.activate(reason="test", source="test")
        broker.close_position.reset_mock()

        # Deactivate should NOT enforce
        ks.deactivate(reason="done", authorized_by="admin")
        assert broker.close_position.call_count == 0
        assert not ks.is_active()

    def test_broker_adapter_none_enforce_returns_early(self, tmp_path: Path):
        """When no broker_adapter, enforce() returns early without error."""
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        # Should not raise
        ks.activate(reason="test", source="test")
        assert ks.is_active()


# ===========================================================================
# TASK 1: Fail-closed on corrupted state
# ===========================================================================


class TestFailClosedOnCorruptedState:
    """Corrupted state value in _get_state_enum() must return ACTIVE (fail-closed)."""

    def test_corrupted_state_value_returns_active(self, tmp_path: Path):
        """If state file has invalid enum value, is_active() must return True."""
        ks_file = tmp_path / "ks.json"
        ks_file.write_text(
            json.dumps(
                {
                    "state": "GARBAGE_VALUE",
                    "killed_classes": [],
                    "reason": "test",
                    "activated_at_utc": None,
                    "authorized_by": "",
                    "history": [],
                }
            )
        )

        ks = KillSwitch(state_file=str(ks_file))
        # Corrupted state → fail-closed → ACTIVE
        assert ks.is_active() is True
        assert ks._get_state_enum() == KillSwitchState.ACTIVE

    def test_empty_state_value_returns_active(self, tmp_path: Path):
        """Empty state string → fail-closed."""
        ks_file = tmp_path / "ks.json"
        ks_file.write_text(
            json.dumps(
                {
                    "state": "",
                    "killed_classes": [],
                    "reason": "",
                    "activated_at_utc": None,
                    "authorized_by": "",
                    "history": [],
                }
            )
        )

        ks = KillSwitch(state_file=str(ks_file))
        assert ks.is_active() is True

    def test_corrupted_json_returns_active(self, tmp_path: Path):
        """Completely corrupted JSON → _load() returns ACTIVE."""
        ks_file = tmp_path / "ks.json"
        ks_file.write_text("{invalid json garbage!!!")

        ks = KillSwitch(state_file=str(ks_file))
        assert ks.is_active() is True

    def test_first_run_no_file_is_inactive(self, tmp_path: Path):
        """Normal first run (no file) → INACTIVE (expected: nothing to protect yet)."""
        ks = KillSwitch(state_file=str(tmp_path / "nonexistent.json"))
        assert not ks.is_active()

    def test_valid_inactive_state_stays_inactive(self, tmp_path: Path):
        """Valid INACTIVE state → not active."""
        ks_file = tmp_path / "ks.json"
        ks_file.write_text(
            json.dumps(
                {
                    "state": "INACTIVE",
                    "killed_classes": [],
                    "reason": "",
                    "activated_at_utc": None,
                    "authorized_by": "",
                    "history": [],
                }
            )
        )

        ks = KillSwitch(state_file=str(ks_file))
        assert not ks.is_active()


# ===========================================================================
# TASK 2: Circuit Breaker → Kill Switch
# ===========================================================================


class TestCircuitBreakerActivatesKillSwitch:
    """record_trade() must activate kill switch when threshold hit."""

    def test_record_trade_activates_kill_switch_on_threshold(self, tmp_path: Path):
        """After threshold consecutive losses, kill switch must be activated."""
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        cb = CircuitBreaker(
            kill_switch=ks,
            config=CircuitBreakerConfig(threshold=3, cooldown_minutes=30),
        )

        # Record 3 consecutive losses (hits threshold=3)
        assert cb.record_trade("metals", -10.0) is False  # 1 loss
        assert cb.record_trade("metals", -20.0) is False  # 2 losses
        assert cb.record_trade("metals", -30.0) is True  # 3 losses → trip

        assert cb.is_open("metals")
        assert ks.is_active(), "Kill switch must be activated on circuit breaker trip"

    def test_record_trade_no_activation_below_threshold(self, tmp_path: Path):
        """Below threshold, kill switch must NOT be activated."""
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        cb = CircuitBreaker(
            kill_switch=ks,
            config=CircuitBreakerConfig(threshold=3, cooldown_minutes=30),
        )

        # 2 losses (below threshold)
        cb.record_trade("metals", -10.0)
        cb.record_trade("metals", -20.0)

        assert not cb.is_open("metals")
        assert not ks.is_active()

    def test_record_trade_profit_resets_counter(self, tmp_path: Path):
        """Profit resets consecutive loss counter, no trip."""
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        cb = CircuitBreaker(
            kill_switch=ks,
            config=CircuitBreakerConfig(threshold=3, cooldown_minutes=30),
        )

        cb.record_trade("metals", -10.0)
        cb.record_trade("metals", -20.0)
        cb.record_trade("metals", 50.0)  # profit resets counter
        cb.record_trade("metals", -10.0)  # back to 1 loss

        assert not cb.is_open("metals")
        assert not ks.is_active()

    def test_record_trade_kill_switch_failure_caught(self):
        """If kill switch activation fails, record_trade must not raise."""
        ks = MagicMock()
        ks.activate.side_effect = RuntimeError("broker offline")

        cb = CircuitBreaker(
            kill_switch=ks,
            config=CircuitBreakerConfig(threshold=2, cooldown_minutes=30),
        )

        # Should not raise despite kill switch failure
        result = cb.record_trade("crypto", -10.0)
        assert result is False  # 1 loss, not yet at threshold

        # Second loss → trip attempt → kill switch fails → no exception
        result = cb.record_trade("crypto", -20.0)
        assert result is True
        ks.activate.assert_called_once()

    def test_trip_activates_kill_switch(self, tmp_path: Path):
        """Manual trip() must also activate kill switch (already working, verify)."""
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        cb = CircuitBreaker(kill_switch=ks)

        cb.trip("forex", reason="manual override")

        assert cb.is_open("forex")
        assert ks.is_active()


# ===========================================================================
# Integration: pre_trade_risk reads kill switch correctly
# ===========================================================================


class TestIntegrationPreTradeRisk:
    """Verify pre_trade_check reads kill switch state after activation."""

    def test_killed_switch_blocks_new_orders(self, tmp_path: Path):
        """When kill switch is ACTIVE, pre_trade_check must reject."""
        from risk.position_sizer_v2 import SizingResult
        from risk.pre_trade_risk import pre_trade_check
        from risk.risk_ledger import RiskLedger
        from risk.risk_policy import RiskPolicy

        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        ks.activate(reason="test", source="test")

        policy = RiskPolicy()
        ledger = MagicMock(spec=RiskLedger)
        ledger.daily_realized_loss = 0
        ledger.weekly_realized_loss = 0
        ledger.total_drawdown = 0
        ledger.open_positions = 0
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0.01"),
            volume_before_round=Decimal("0.01"),
            risk_amount=Decimal("100"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("100"),
            margin_estimate=Decimal("50"),
            rejected=False,
            rejection_reasons=[],
        )

        result = pre_trade_check(
            sizing_result=sizing,
            risk_policy=policy,
            risk_ledger=ledger,
            account_equity=10000,
            kill_switch=ks,
        )

        assert not result.approved
        assert any("Kill switch" in r for r in result.reasons)
