"""Comprehensive unit tests for all risk modules.

Covers: KillSwitch, CircuitBreaker, MarketSessionGuard, AutoStop, PreTradeRiskGate.
Total: 36 tests.
"""

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.risk.auto_stop import AutoStop
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.risk.kill_switch import (
    CloseMode,
    KillSwitch,
)
from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate, price_sanity_check

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def kill_switch_file(tmp_dir):
    return str(tmp_dir / "kill_switch_state.json")


@pytest.fixture
def cb_state_file(tmp_dir):
    return str(tmp_dir / "circuit_breaker_state.json")


@pytest.fixture
def auto_stop_file(tmp_dir):
    return str(tmp_dir / "auto_stop_state.json")


@pytest.fixture
def ks(kill_switch_file):
    return KillSwitch(state_file=kill_switch_file)


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.get_positions.return_value = []
    return broker


@pytest.fixture
def cb(cb_state_file):
    return CircuitBreaker(state_file=cb_state_file)


@pytest.fixture
def auto_stop(auto_stop_file):
    return AutoStop(state_file=auto_stop_file)


@pytest.fixture
def gate():
    """PreTradeRiskGate with mock kill_switch and circuit_breaker (both inactive)."""
    mock_ks = MagicMock()
    mock_ks.is_active.return_value = False
    mock_ks.is_paused.return_value = False
    mock_cb = MagicMock()
    mock_cb.is_open.return_value = False
    return PreTradeRiskGate(kill_switch=mock_ks, circuit_breaker=mock_cb)


# ===================================================================
# 1. Kill Switch — 10 tests
# ===================================================================


class TestKillSwitch:
    def test_activate_deactivate_cycle(self, ks):
        assert not ks.is_active()
        ks.activate(reason="test activate")
        assert ks.is_active()
        assert ks.is_triggered
        ks.deactivate(reason="test deactivate")
        assert not ks.is_active()
        assert not ks.is_triggered

    def test_state_persistence_across_restarts(self, kill_switch_file):
        ks1 = KillSwitch(state_file=kill_switch_file)
        ks1.activate(reason="persist test")
        assert ks1.is_active()

        ks2 = KillSwitch(state_file=kill_switch_file)
        assert ks2.is_active()
        assert ks2.get_status()["reason"] == "persist test"

    def test_fail_closed_on_corrupted_state(self, tmp_dir):
        bad_file = tmp_dir / "bad_state.json"
        bad_file.write_text("NOT JSON {{{")
        ks = KillSwitch(state_file=str(bad_file))
        assert ks.is_active()

    def test_telegram_kill_all_command(self, ks, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "12345")
        ks._allowed_users = ks._load_allowed_users()
        result = ks.handle_command("/kill_all", user_id=12345)
        assert "KILL SWITCH ACTIVATED" in result
        assert ks.is_active()

    def test_telegram_pause_and_resume(self, ks, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "12345")
        ks._allowed_users = ks._load_allowed_users()
        result = ks.handle_command("/pause", user_id=12345)
        assert "PAUSED" in result
        assert ks.is_paused()
        result = ks.handle_command("/resume", user_id=12345)
        assert "RESUMED" in result
        assert not ks.is_triggered

    def test_enforce_close_all(self, ks, mock_broker):
        mock_broker.get_positions.return_value = [
            {"ticket": 101, "pnl": 100.0},
            {"ticket": 102, "pnl": -50.0},
        ]
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)
        assert len(result["closed"]) == 2
        assert 101 in result["closed"]
        assert 102 in result["closed"]
        assert mock_broker.close_position.call_count == 2

    def test_enforce_close_risk_increasing_only(self, ks, mock_broker):
        mock_broker.get_positions.return_value = [
            {"ticket": 201, "pnl": 200.0},
            {"ticket": 202, "pnl": -30.0},
            {"ticket": 203, "pnl": -10.0},
        ]
        result = ks.enforce(CloseMode.CLOSE_RISK_INCREASING_ONLY, broker_adapter=mock_broker)
        assert 201 not in result["closed"]
        assert 202 in result["closed"]
        assert 203 in result["closed"]
        assert 201 in result["remaining"]

    def test_enforce_no_new_orders_only(self, ks, mock_broker):
        mock_broker.get_positions.return_value = [
            {"ticket": 301, "pnl": -100.0},
        ]
        result = ks.enforce(CloseMode.NO_NEW_ORDERS_ONLY, broker_adapter=mock_broker)
        assert len(result["closed"]) == 0
        assert 301 in result["remaining"]

    def test_idempotent_close_tracking(self, ks, mock_broker):
        mock_broker.get_positions.return_value = [{"ticket": 401, "pnl": -10.0}]
        result1 = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)
        assert 401 in result1["closed"]
        assert mock_broker.close_position.call_count == 1

        mock_broker.get_positions.return_value = [{"ticket": 401, "pnl": -10.0}]
        result2 = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)
        assert 401 in result2["closed"]
        assert mock_broker.close_position.call_count == 1

    def test_broker_reconciliation(self, ks, mock_broker):
        # After close, positions should be empty for reconciliation
        mock_broker.get_positions.return_value = [{"ticket": 501, "pnl": -20.0}]
        result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)
        # Reconciliation checks if positions are gone; mock still returns them
        # so reconciliation fails (expected with static mock)
        assert result["reconciled"] is False

    def test_unauthorized_user_rejection(self, ks, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "11111")
        ks._allowed_users = ks._load_allowed_users()
        result = ks.handle_command("/kill_all", user_id=99999)
        assert "UNAUTHORIZED" in result
        assert not ks.is_active()


# ===================================================================
# 2. Circuit Breaker — 8 tests
# ===================================================================


class TestCircuitBreaker:
    def test_consecutive_loss_tracking(self, cb):
        cb.record_trade("forex", pnl=100.0)
        status = cb.get_status()
        assert status["forex"]["consecutive_losses"] == 0

        cb.record_trade("forex", pnl=-10.0)
        status = cb.get_status()
        assert status["forex"]["consecutive_losses"] == 1

        cb.record_trade("forex", pnl=-20.0)
        status = cb.get_status()
        assert status["forex"]["consecutive_losses"] == 2

    def test_threshold_activation(self, cb):
        for _ in range(3):
            cb.record_trade("metals", pnl=-10.0)
        assert cb.is_open("metals")
        assert cb.is_blocked

    def test_cooldown_recovery(self, cb):
        cb._classes["crypto"].open = True
        cb._classes["crypto"].opened_at = time.time() - 999999
        cb._classes["crypto"].consecutive_losses = 5
        assert not cb.is_open("crypto")

    def test_integration_with_kill_switch(self, cb_state_file):
        mock_ks = MagicMock()
        cb = CircuitBreaker(state_file=cb_state_file, kill_switch=mock_ks)
        cb.trip("forex", reason="manual test")
        mock_ks.activate.assert_called_once()

    def test_state_persistence(self, cb_state_file):
        cb1 = CircuitBreaker(state_file=cb_state_file)
        for _ in range(3):
            cb1.record_trade("indices", pnl=-5.0)
        assert cb1.is_open("indices")

        cb2 = CircuitBreaker(state_file=cb_state_file)
        assert cb2.is_open("indices")

    def test_fail_closed_on_corruption(self, tmp_dir):
        bad_file = tmp_dir / "bad_cb.json"
        bad_file.write_text("{corrupt json!!!")
        cb = CircuitBreaker(state_file=str(bad_file))
        assert cb.is_open("forex")
        assert cb.is_open("metals")
        assert cb.is_blocked

    def test_per_asset_class_tracking(self, cb):
        for _ in range(3):
            cb.record_trade("forex", pnl=-1.0)
        assert cb.is_open("forex")
        assert not cb.is_open("metals")
        assert not cb.is_open("crypto")

    def test_auto_recovery_after_cooldown(self, cb):
        for _ in range(3):
            cb.record_trade("metals", pnl=-10.0)
        assert cb.is_open("metals")
        cb._classes["metals"].opened_at = time.time() - 999999
        assert not cb.is_open("metals")
        status = cb.get_status()
        assert status["metals"]["consecutive_losses"] == 0


# ===================================================================
# 3. Market Session Guard — 8 tests
# ===================================================================

from graxia.packages.quant_os.risk.market_session_guard import MarketSessionGuard


class TestMarketSessionGuard:
    def test_forex_trading_hours(self):
        guard = MarketSessionGuard(check_holidays=False)
        # 2025-07-01 15:00 UTC — within forex session (01:00–21:55)
        t = datetime(2025, 7, 1, 15, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now=t)
        assert result.allowed is True
        assert result.market_open is True

    def test_indices_trading_hours_restricted(self):
        guard = MarketSessionGuard(check_holidays=False)
        # 2025-07-01 10:00 UTC — before indices session (13:00–21:00)
        t = datetime(2025, 7, 1, 10, 0, tzinfo=UTC)
        result = guard.check("US30", now=t)
        assert result.allowed is False
        assert "Outside trading session" in result.reason

    def test_metals_trading_hours(self):
        guard = MarketSessionGuard(check_holidays=False)
        # 2025-07-01 15:00 UTC — within metals session (01:00–21:55)
        t = datetime(2025, 7, 1, 15, 0, tzinfo=UTC)
        result = guard.check("XAUUSD", now=t)
        assert result.allowed is True

    def test_crypto_24_7(self):
        guard = MarketSessionGuard(check_holidays=False)
        # 2025-07-01 03:00 UTC — any time works for crypto
        t = datetime(2025, 7, 1, 3, 0, tzinfo=UTC)
        result = guard.check("BTCUSD", now=t)
        assert result.allowed is True
        assert result.session == "24/7"

    def test_rollover_window_blocking(self):
        guard = MarketSessionGuard(check_holidays=False)
        # 2025-07-01 22:00 UTC — inside rollover (21:55–22:16)
        t = datetime(2025, 7, 1, 22, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now=t)
        assert result.allowed is False
        assert result.in_rollover is True

    def test_low_liquidity_buffer(self):
        guard = MarketSessionGuard(buffer_minutes=5, check_holidays=False)
        # 2025-07-01 01:02 UTC — within 5min of forex open (01:00)
        t = datetime(2025, 7, 1, 1, 2, tzinfo=UTC)
        result = guard.check("GBPUSD", now=t)
        assert result.allowed is False
        assert result.in_buffer is True

    def test_holiday_detection_via_mt5(self):
        mock_mt5 = MagicMock()
        mock_info = MagicMock()
        mock_info.trade_mode = 0
        mock_mt5.symbol_info.return_value = mock_info

        guard = MarketSessionGuard(mt5=mock_mt5, check_holidays=True)
        t = datetime(2025, 7, 1, 15, 0, tzinfo=UTC)
        result = guard.check("EURUSD", now=t)
        assert result.allowed is False
        assert "DISABLED" in result.reason

    def test_mt5_trade_mode_check(self):
        mock_mt5 = MagicMock()
        mock_info = MagicMock()
        mock_info.trade_mode = 1
        mock_info.trade_allowed = True
        mock_mt5.symbol_info.return_value = mock_info

        guard = MarketSessionGuard(mt5=mock_mt5, check_holidays=True)
        t = datetime(2025, 7, 1, 15, 0, tzinfo=UTC)
        result = guard.check("XAUUSD", now=t)
        assert result.allowed is False
        assert "restricted" in result.reason


# ===================================================================
# 4. Auto-Stop — 5 tests
# ===================================================================


class TestAutoStop:
    def test_hwm_tracking(self, auto_stop):
        auto_stop.update_equity(10000.0)
        assert auto_stop.high_water_mark == 10000.0
        auto_stop.update_equity(12000.0)
        assert auto_stop.high_water_mark == 12000.0
        auto_stop.update_equity(11000.0)
        assert auto_stop.high_water_mark == 12000.0

    def test_15_percent_drawdown_threshold(self, auto_stop):
        auto_stop.update_equity(10000.0)
        result = auto_stop.update_equity(8400.0)
        assert auto_stop.is_triggered is True
        assert result["triggered"] is True

    def test_kill_switch_activation_on_breach(self, auto_stop_file):
        mock_ks = MagicMock()
        auto_stop = AutoStop(
            kill_switch=mock_ks,
            threshold_pct=15.0,
            state_file=auto_stop_file,
        )
        auto_stop.update_equity(10000.0)
        auto_stop.update_equity(8400.0)
        mock_ks.activate.assert_called_once()

    def test_manual_reset(self, auto_stop):
        auto_stop.update_equity(10000.0)
        auto_stop.update_equity(8400.0)
        assert auto_stop.is_triggered is True
        result = auto_stop.reset(authorized_by="admin", reason="manual reset")
        assert auto_stop.is_triggered is False
        assert result["status"] == "reset"

    def test_state_persistence(self, auto_stop_file):
        as1 = AutoStop(state_file=auto_stop_file)
        as1.update_equity(10000.0)
        as1.update_equity(8400.0)
        assert as1.is_triggered is True

        as2 = AutoStop(state_file=auto_stop_file)
        assert as2.is_triggered is True


# ===================================================================
# 5. Pre-Trade Gate — 5 tests
# ===================================================================


class TestPreTradeGate:
    def test_kill_switch_check_blocks(self, gate):
        mock_ks = MagicMock()
        mock_ks.is_active.return_value = True
        mock_ks.is_paused.return_value = False
        gate._kill_switch = mock_ks
        order = MagicMock(symbol="EURUSD", asset_class="forex")
        result = gate.check_order_sync(order)
        assert result.passed is False
        assert "Kill switch is active" in result.reason

    def test_circuit_breaker_check_blocks(self, gate):
        mock_cb = MagicMock()
        mock_cb.is_open.return_value = True
        gate._circuit_breaker = mock_cb
        order = MagicMock(symbol="EURUSD", asset_class="forex")
        result = gate.check_order_sync(order)
        assert result.passed is False
        assert "Circuit breaker open" in result.reason

    def test_price_sanity_check_rejects(self, gate):
        # Prices around 100 with small variance, but current_price=200 is far away
        prices = [100.0 + i * 0.5 for i in range(20)]
        passed, reason = price_sanity_check(
            current_price=200.0,
            recent_prices=prices,
            max_std_deviations=3.0,
            sma_period=20,
        )
        assert passed is False
        assert "Price anomaly" in reason

    def test_combined_gate_logic_all_pass(self, gate):
        order = MagicMock(symbol="EURUSD", asset_class="forex")
        result = gate.check_order_sync(order)
        assert result.passed is True

    def test_fail_closed_on_exception(self, gate):
        mock_ks = MagicMock()
        mock_ks.is_active.side_effect = RuntimeError("broker down")
        gate._kill_switch = mock_ks
        order = MagicMock(symbol="EURUSD", asset_class="forex")
        result = gate.check_order_sync(order)
        assert result.passed is False
        assert "Kill switch error" in result.reason
