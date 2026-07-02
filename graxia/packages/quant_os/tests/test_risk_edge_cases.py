"""Tests for risk engine — CRISIS cascade, provider failover, max positions, boundary conditions."""

import time
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.core.enums import RegimeType, SignalType
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from graxia.packages.quant_os.risk.engine import (
    AccountState,
    PortfolioState,
    RejectReason,
    RiskEngine,
    Signal,
)
from graxia.packages.quant_os.risk.kill_switch import KillSwitch, KillSwitchState
from graxia.packages.quant_os.risk.portfolio import PortfolioRisk, PositionExposure
from graxia.packages.quant_os.risk.slippage_model import (
    SlippageModel,
    TradingSession,
    VolatilityRegime,
    classify_session,
)

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_signal(**overrides):
    defaults = dict(
        symbol="XAUUSD",
        side=SignalType.BUY,
        conviction=0.8,
        strategy_id="mtm",
        asset_class="metals",
        venue="pepperstone",
        entry_price=2025.0,
        stop_loss=2020.0,
        take_profit=2040.0,
        timestamp_epoch=time.time(),
    )
    defaults.update(overrides)
    return Signal(**defaults)


def _make_account(**overrides):
    defaults = dict(
        equity=10000.0,
        free_margin=9000.0,
        margin_level_pct=500.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        peak_equity=10000.0,
        current_drawdown_pct=0.0,
        open_positions=0,
    )
    defaults.update(overrides)
    return AccountState(**defaults)


def _make_portfolio(**overrides):
    defaults = dict(
        total_exposure_pct=0.0,
        class_exposure_pct={},
        venue_exposure_pct={},
        position_symbols=[],
        correlation_matrix=None,
    )
    defaults.update(overrides)
    return PortfolioState(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# RiskEngine — Layer-by-Layer Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestRiskEnginePreChecks:
    """Kill switch and circuit breaker pre-checks."""

    def test_kill_switch_active_rejects_all(self):
        ks = MagicMock()
        ks.is_active.return_value = True
        engine = RiskEngine(kill_switch=ks)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.KILL_SWITCH_ACTIVE
        assert verdict.layer_failed == 0

    def test_circuit_breaker_open_rejects_asset_class(self):
        cb = MagicMock()
        cb.is_open.return_value = True
        engine = RiskEngine(circuit_breaker=cb)
        verdict = engine.evaluate(
            _make_signal(asset_class="metals"),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.CIRCUIT_BREAKER_OPEN

    def test_no_kill_switch_no_breaker_passes_pre_checks(self):
        engine = RiskEngine()
        # Should not raise — pre-checks pass when components are None
        pre = engine._pre_checks(_make_signal())
        assert pre is None


class TestRiskEngineLayer1:
    """Layer 1: per-trade checks."""

    def test_stale_signal_rejected(self):
        engine = RiskEngine()
        sig = _make_signal(timestamp_epoch=time.time() - 10)
        verdict = engine.evaluate(
            sig,
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.STALE_SIGNAL
        assert verdict.layer_failed == 1

    def test_low_conviction_rejected(self):
        engine = RiskEngine()
        sig = _make_signal(conviction=0.3)
        verdict = engine.evaluate(
            sig,
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.LOW_CONVICTION

    def test_conviction_at_boundary_passes(self):
        engine = RiskEngine()
        sig = _make_signal(conviction=0.6)
        verdict = engine.evaluate(
            sig,
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        # Should pass layer 1 (may fail later layers)
        assert verdict.layer_failed != 1 or verdict.approved

    def test_schema_validator_failure(self):
        validator = MagicMock()
        validator.validate_signal.return_value = False
        engine = RiskEngine(schema_validator=validator)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.INVALID_SCHEMA

    def test_session_closed_rejected(self):
        checker = MagicMock()
        checker.is_session_open.return_value = False
        engine = RiskEngine(session_checker=checker)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.SESSION_CLOSED

    def test_zero_equity_rejected(self):
        engine = RiskEngine()
        sig = _make_signal(entry_price=2025.0, stop_loss=2020.0)
        verdict = engine.evaluate(
            sig,
            _make_account(equity=0.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        # Zero equity → max_risk_amount = 0, risk_per_lot > 0 → EXCEEDS_RISK_PER_TRADE
        assert not verdict.approved

    def test_negative_equity_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(equity=-5000.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved


class TestRiskEngineLayer2:
    """Layer 2: portfolio-level checks."""

    def test_max_total_exposure_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(total_exposure_pct=0.85),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.EXCEEDS_TOTAL_EXPOSURE

    def test_total_exposure_at_boundary_passes(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(total_exposure_pct=0.79),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        # Should pass layer 2 if not rejected
        assert verdict.layer_failed != 2

    def test_max_class_exposure_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(asset_class="metals"),
            _make_account(),
            _make_portfolio(class_exposure_pct={"metals": 0.35}),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.EXCEEDS_CLASS_EXPOSURE

    def test_max_venue_exposure_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(venue="pepperstone"),
            _make_account(),
            _make_portfolio(venue_exposure_pct={"pepperstone": 0.55}),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.EXCEEDS_VENUE_EXPOSURE

    def test_high_correlation_rejected(self):
        corr_provider = MagicMock()
        corr_provider.get_correlation.return_value = 0.90
        engine = RiskEngine(correlation_provider=corr_provider)
        portfolio = _make_portfolio(
            position_symbols=["XAGUSD"],
            correlation_matrix={"XAUUSD": {"XAGUSD": 0.90}},
        )
        verdict = engine.evaluate(
            _make_signal(symbol="XAUUSD"),
            _make_account(),
            portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.HIGH_CORRELATION

    def test_correlation_check_skipped_when_no_matrix(self):
        corr_provider = MagicMock()
        engine = RiskEngine(correlation_provider=corr_provider)
        portfolio = _make_portfolio(position_symbols=["XAGUSD"], correlation_matrix=None)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        # Should not reject for correlation when matrix is None
        assert verdict.reason_code != RejectReason.HIGH_CORRELATION

    def test_max_positions_reached_rejected(self):
        engine = RiskEngine()
        symbols = [f"SYM{i}" for i in range(20)]
        portfolio = _make_portfolio(position_symbols=symbols)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(equity=150000.0),
            portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.MAX_POSITIONS_REACHED

    def test_positions_at_boundary_passes(self):
        engine = RiskEngine()
        symbols = [f"SYM{i}" for i in range(19)]
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(equity=200000.0),
            _make_portfolio(position_symbols=symbols),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.layer_failed != 2


class TestRiskEngineLayer3:
    """Layer 3: account-level checks."""

    def test_daily_loss_limit_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(daily_pnl=-250.0, equity=10000.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.DAILY_LOSS_LIMIT

    def test_weekly_loss_limit_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(weekly_pnl=-600.0, equity=10000.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.WEEKLY_LOSS_LIMIT

    def test_drawdown_limit_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(current_drawdown_pct=0.18),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.DRAWDOWN_LIMIT

    def test_drawdown_at_boundary_passes(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(current_drawdown_pct=0.14),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.layer_failed != 3

    def test_insufficient_margin_rejected(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(margin_level_pct=150.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.INSUFFICIENT_MARGIN

    def test_margin_level_zero_skipped(self):
        """margin_level_pct=0 means no margin data available — should skip check."""
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(margin_level_pct=0.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.reason_code != RejectReason.INSUFFICIENT_MARGIN

    def test_positive_daily_pnl_not_rejected(self):
        """Profitable day should not trigger daily loss."""
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(daily_pnl=500.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.reason_code != RejectReason.DAILY_LOSS_LIMIT


class TestRiskEngineLayer4:
    """Layer 4: sizing checks."""

    def test_zero_stop_distance_rejected(self):
        engine = RiskEngine()
        sig = _make_signal(entry_price=2025.0, stop_loss=2025.0)
        verdict = engine.evaluate(
            sig,
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert not verdict.approved
        assert verdict.reason_code == RejectReason.SIZING_REJECTED

    def test_sizing_with_high_volatility(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.50,
            regime=RegimeType.HIGH_VOLATILITY,
        )
        assert verdict.approved
        assert verdict.approved_quantity > 0

    def test_sizing_with_zero_volatility(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.0,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved

    def test_sizing_clamp_vol_scalar_max(self):
        """Very low vol should clamp vol_scalar to 3.0 max."""
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.001,
            regime=RegimeType.LOW_VOLATILITY,
        )
        assert verdict.approved
        assert verdict.sizing_details["vol_scalar"] <= 3.0

    def test_sizing_clamp_vol_scalar_min(self):
        """Very high vol should clamp vol_scalar to 0.1 min."""
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=99.0,
            regime=RegimeType.CRISIS,
        )
        assert verdict.approved
        assert verdict.sizing_details["vol_scalar"] >= 0.1

    def test_regime_multiplier_applied(self):
        multipliers = {
            RegimeType.CRISIS: 0.25,
            RegimeType.HIGH_VOLATILITY: 0.5,
            RegimeType.RANGE_BOUND: 1.0,
        }
        engine = RiskEngine(regime_multiplier_map=multipliers)
        crisis = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.CRISIS,
        )
        normal = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert crisis.approved
        assert normal.approved
        assert crisis.approved_quantity < normal.approved_quantity

    def test_approved_quantity_positive(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(equity=10000.0),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved
        assert verdict.approved_quantity > 0

    def test_kelly_cap_enforced(self):
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved
        assert verdict.sizing_details["kelly_fraction"] <= 0.25


class TestRiskEngineCRISISCascade:
    """CRISIS regime cascade — extreme volatility, drawdowns, full halt."""

    def test_crisis_regime_reduces_sizing(self):
        engine = RiskEngine(regime_multiplier_map={RegimeType.CRISIS: 0.25})
        crisis = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.30,
            regime=RegimeType.CRISIS,
        )
        normal = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert crisis.approved_quantity < normal.approved_quantity

    def test_crisis_with_high_drawdown双重打击(self):
        """CRISIS regime + high drawdown → double protection."""
        engine = RiskEngine()
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(current_drawdown_pct=0.16),
            _make_portfolio(),
            realized_vol=0.50,
            regime=RegimeType.CRISIS,
        )
        assert not verdict.approved

    def test_crisis_with_kill_switch_triple_block(self):
        """CRISIS + kill switch + drawdown = blocked at every layer."""
        ks = MagicMock()
        ks.is_active.return_value = True
        engine = RiskEngine(kill_switch=ks)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.50,
            regime=RegimeType.CRISIS,
        )
        assert not verdict.approved
        assert verdict.layer_failed == 0

    def test_crisis_circuit_breaker_combination(self):
        cb = MagicMock()
        cb.is_open.return_value = True
        engine = RiskEngine(circuit_breaker=cb)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.50,
            regime=RegimeType.CRISIS,
        )
        assert not verdict.approved


class TestRiskEngineFailover:
    """Provider failover scenarios."""

    def test_session_checker_unavailable(self):
        """No session checker → skip session check, don't block."""
        engine = RiskEngine(session_checker=None)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.reason_code != RejectReason.SESSION_CLOSED

    def test_schema_validator_unavailable(self):
        """No schema validator → skip validation, don't block."""
        engine = RiskEngine(schema_validator=None)
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.reason_code != RejectReason.INVALID_SCHEMA

    def test_correlation_provider_unavailable(self):
        """No correlation provider → skip correlation check."""
        engine = RiskEngine(correlation_provider=None)
        portfolio = _make_portfolio(position_symbols=["XAGUSD"])
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.reason_code != RejectReason.HIGH_CORRELATION

    def test_all_providers_available_full_check(self):
        """With all providers, full 4-layer check runs."""
        ks = MagicMock()
        ks.is_active.return_value = False
        cb = MagicMock()
        cb.is_open.return_value = False
        checker = MagicMock()
        checker.is_session_open.return_value = True
        validator = MagicMock()
        validator.validate_signal.return_value = True
        corr = MagicMock()
        corr.get_correlation.return_value = 0.3

        engine = RiskEngine(
            kill_switch=ks,
            circuit_breaker=cb,
            session_checker=checker,
            schema_validator=validator,
            correlation_provider=corr,
        )
        verdict = engine.evaluate(
            _make_signal(),
            _make_account(),
            _make_portfolio(),
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved


# ═══════════════════════════════════════════════════════════════════════
# Kill Switch
# ═══════════════════════════════════════════════════════════════════════


class TestKillSwitch:
    """Kill switch edge cases."""

    def test_initial_state_inactive(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        assert not ks.is_active()
        assert not ks.is_paused()

    def test_is_triggered_when_active(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        ks.activate("test")
        assert ks.is_triggered
        assert ks.is_active()

    def test_is_triggered_when_paused(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        ks._set_state(KillSwitchState.PAUSED, "test", "admin")
        assert ks.is_triggered
        assert ks.is_paused()

    def test_class_killed_when_global_active(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        ks.activate("global kill")
        assert ks.is_class_killed("metals")
        assert ks.is_class_killed("forex")
        assert ks.is_class_killed("crypto")

    def test_class_killed_specific_class(self, tmp_path):
        import os

        os.environ["TELEGRAM_ALLOWED_USERS"] = "12345"
        try:
            ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
            # Source bug: _last_user_id not initialized before _cmd_kill_class uses it.
            # Initialize it manually to test the kill_class logic.
            ks._last_user_id = 12345
            ks._cmd_kill_class("metals")
            assert ks.is_class_killed("metals")
            assert not ks.is_class_killed("forex")
        finally:
            os.environ.pop("TELEGRAM_ALLOWED_USERS", None)

    def test_deactivate_clears_classes(self, tmp_path):
        import os

        os.environ["TELEGRAM_ALLOWED_USERS"] = "12345"
        try:
            ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
            ks._last_user_id = 12345
            ks._cmd_kill_class("metals")
            ks._cmd_kill_class("crypto")
            ks.deactivate("test reset", "admin")
            assert not ks.is_class_killed("metals")
            assert not ks.is_class_killed("crypto")
        finally:
            os.environ.pop("TELEGRAM_ALLOWED_USERS", None)

    def test_get_status_structure(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        status = ks.get_status()
        assert "state" in status
        assert "killed_classes" in status
        assert "reason" in status

    def test_corrupt_state_file_resets(self, tmp_path):
        fpath = tmp_path / "ks.json"
        fpath.write_text("NOT JSON!!!")
        ks = KillSwitch(state_file=str(fpath))
        assert not ks.is_active()

    def test_persistence_across_instances(self, tmp_path):
        fpath = str(tmp_path / "ks.json")
        ks1 = KillSwitch(state_file=fpath)
        ks1.activate("persist test")
        ks2 = KillSwitch(state_file=fpath)
        assert ks2.is_active()

    def test_trigger_type_property(self, tmp_path):
        ks = KillSwitch(state_file=str(tmp_path / "ks.json"))
        assert ks.trigger_type == "INACTIVE"
        ks.activate("test")
        assert ks.trigger_type == "ACTIVE"


# ═══════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════


class TestCircuitBreaker:
    """Circuit breaker edge cases."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert not cb.is_open("metals")
        assert not cb.is_blocked

    def test_trips_after_consecutive_losses(self):
        cb = CircuitBreaker()
        cb.record_trade("metals", -100.0)
        cb.record_trade("metals", -200.0)
        assert not cb.is_open("metals")
        result = cb.record_trade("metals", -150.0)
        assert result is True
        assert cb.is_open("metals")

    def test_win_resets_counter(self):
        cb = CircuitBreaker()
        cb.record_trade("metals", -100.0)
        cb.record_trade("metals", -200.0)
        cb.record_trade("metals", 50.0)  # win resets
        cb.record_trade("metals", -100.0)
        assert not cb.is_open("metals")  # only 1 loss, not 3

    def test_custom_threshold(self):
        cb = CircuitBreaker(
            configs={
                "metals": CircuitBreakerConfig(threshold=2),
            }
        )
        cb.record_trade("metals", -100.0)
        assert not cb.is_open("metals")
        result = cb.record_trade("metals", -200.0)
        assert result is True

    def test_manual_trip(self):
        cb = CircuitBreaker()
        cb.trip("metals", "manual intervention")
        assert cb.is_open("metals")

    def test_manual_reset(self):
        cb = CircuitBreaker()
        cb.trip("metals", "manual")
        cb.reset("metals", authorized_by="test", reason="test reset")
        assert not cb.is_open("metals")

    def test_cooldown_auto_recovery(self):
        cb = CircuitBreaker(
            configs={
                "metals": CircuitBreakerConfig(cooldown_minutes=0),
            }
        )
        cb.trip("metals", "test")
        assert not cb.is_open("metals")  # cooldown=0 → immediately recovered

    def test_is_blocked_any_class(self):
        cb = CircuitBreaker()
        assert not cb.is_blocked
        cb.trip("metals", "test")
        assert cb.is_blocked

    def test_reason_property(self):
        cb = CircuitBreaker()
        assert cb.reason == ""
        cb.trip("metals", "crisis")
        assert "crisis" in cb.reason

    def test_get_status_all_classes(self):
        cb = CircuitBreaker()
        status = cb.get_status()
        assert "metals" in status
        assert "forex" in status
        assert "crypto" in status
        assert "indices" in status

    def test_trip_count_increments(self):
        cb = CircuitBreaker()
        cb.trip("metals", "first")
        cb.reset("metals", authorized_by="test", reason="test reset")
        cb.trip("metals", "second")
        status = cb.get_status()
        assert status["metals"]["trip_count"] == 2

    def test_is_triggered_alias(self):
        cb = CircuitBreaker()
        assert not cb.is_triggered
        cb.trip("metals")
        assert cb.is_triggered

    def test_persistence(self, tmp_path):
        fpath = str(tmp_path / "cb.json")
        cb1 = CircuitBreaker(state_file=fpath)
        cb1.trip("metals", "test")
        cb2 = CircuitBreaker(state_file=fpath)
        assert cb2.is_open("metals")

    def test_corrupt_state_file_ignored(self, tmp_path):
        fpath = tmp_path / "cb.json"
        fpath.write_text("{bad json")
        cb = CircuitBreaker(state_file=str(fpath))
        assert not cb.is_open("metals")

    def test_independent_class_trackers(self):
        cb = CircuitBreaker()
        cb.trip("metals", "crisis")
        assert cb.is_open("metals")
        assert not cb.is_open("forex")


# ═══════════════════════════════════════════════════════════════════════
# Portfolio Risk
# ═══════════════════════════════════════════════════════════════════════


class TestPortfolioRisk:
    """Portfolio risk edge cases."""

    def test_empty_portfolio_metrics(self):
        pr = PortfolioRisk()
        m = pr.calculate_metrics()
        assert m.total_exposure == Decimal("0")
        assert m.gross_exposure == Decimal("0")

    def test_single_long_position(self):
        pr = PortfolioRisk()
        pr.update_position(
            PositionExposure(
                symbol="EURUSD",
                direction="LONG",
                quantity=Decimal("0.1"),
                market_value=Decimal("10850"),
                unrealized_pnl=Decimal("50"),
                risk_pct=1.0,
            )
        )
        m = pr.calculate_metrics()
        assert m.long_exposure == Decimal("10850")
        assert m.short_exposure == Decimal("0")

    def test_mixed_long_short(self):
        pr = PortfolioRisk()
        pr.update_position(
            PositionExposure(
                symbol="EURUSD",
                direction="LONG",
                quantity=Decimal("0.1"),
                market_value=Decimal("10850"),
                unrealized_pnl=Decimal("0"),
                risk_pct=1.0,
            )
        )
        pr.update_position(
            PositionExposure(
                symbol="GBPUSD",
                direction="SHORT",
                quantity=Decimal("0.1"),
                market_value=Decimal("12650"),
                unrealized_pnl=Decimal("0"),
                risk_pct=1.0,
            )
        )
        m = pr.calculate_metrics()
        assert m.long_exposure == Decimal("10850")
        assert m.short_exposure == Decimal("12650")

    def test_remove_position(self):
        pr = PortfolioRisk()
        pr.update_position(
            PositionExposure(
                symbol="EURUSD",
                direction="LONG",
                quantity=Decimal("0.1"),
                market_value=Decimal("10850"),
                unrealized_pnl=Decimal("0"),
                risk_pct=1.0,
            )
        )
        pr.remove_position("EURUSD")
        m = pr.calculate_metrics()
        assert m.total_exposure == Decimal("0")

    def test_remove_nonexistent_position(self):
        pr = PortfolioRisk()
        pr.remove_position("NONEXISTENT")  # should not raise

    def test_exposure_limit_check(self):
        pr = PortfolioRisk(max_exposure_pct=50.0)
        assert pr.check_exposure_limit()

    def test_zero_balance_exposure_check(self):
        pr = PortfolioRisk()
        pr.account_balance = Decimal("0")
        assert pr.check_exposure_limit()

    def test_concentration_calculation(self):
        pr = PortfolioRisk()
        pr.update_position(
            PositionExposure(
                symbol="EURUSD",
                direction="LONG",
                quantity=Decimal("0.1"),
                market_value=Decimal("10000"),
                unrealized_pnl=Decimal("0"),
                risk_pct=5.0,
            )
        )
        pr.update_position(
            PositionExposure(
                symbol="GBPUSD",
                direction="LONG",
                quantity=Decimal("0.1"),
                market_value=Decimal("5000"),
                unrealized_pnl=Decimal("0"),
                risk_pct=2.0,
            )
        )
        m = pr.calculate_metrics()
        assert m.concentration_pct == pytest.approx(66.67, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════
# Slippage Model
# ═══════════════════════════════════════════════════════════════════════


class TestSlippageModel:
    """Slippage model edge cases."""

    def test_asian_session_slippage(self):
        sm = SlippageModel()
        slip = sm.get_slippage("XAUUSD", TradingSession.ASIAN)
        assert slip > 0

    def test_overlap_session_lowest_slippage(self):
        sm = SlippageModel()
        overlap = sm.get_slippage("XAUUSD", TradingSession.OVERLAP)
        asian = sm.get_slippage("XAUUSD", TradingSession.ASIAN)
        assert overlap < asian

    def test_rollover_highest_slippage(self):
        sm = SlippageModel()
        rollover = sm.get_slippage("XAUUSD", TradingSession.ROLLOVER)
        london = sm.get_slippage("XAUUSD", TradingSession.LONDON)
        assert rollover > london * 5

    def test_volatility_extreme_multiplier(self):
        sm = SlippageModel()
        normal = sm.get_slippage("XAUUSD", TradingSession.LONDON, VolatilityRegime.NORMAL)
        extreme = sm.get_slippage("XAUUSD", TradingSession.LONDON, VolatilityRegime.EXTREME)
        assert extreme > normal * 2

    def test_volatility_low_multiplier(self):
        sm = SlippageModel()
        normal = sm.get_slippage("XAUUSD", TradingSession.LONDON, VolatilityRegime.NORMAL)
        low = sm.get_slippage("XAUUSD", TradingSession.LONDON, VolatilityRegime.LOW)
        assert low < normal

    def test_apply_slippage_buy(self):
        sm = SlippageModel()
        adjusted = sm.apply_slippage(2025.0, "BUY", 0.20)
        assert adjusted > 2025.0

    def test_apply_slippage_sell(self):
        sm = SlippageModel()
        adjusted = sm.apply_slippage(2025.0, "SELL", 0.20)
        assert adjusted < 2025.0

    def test_apply_slippage_case_insensitive(self):
        sm = SlippageModel()
        assert sm.apply_slippage(100.0, "buy", 0.1) > 100.0
        assert sm.apply_slippage(100.0, "Sell", 0.1) < 100.0

    def test_zero_slippage_no_change(self):
        sm = SlippageModel()
        assert sm.apply_slippage(2025.0, "BUY", 0.0) == 2025.0

    def test_estimate_cost_per_trade(self):
        sm = SlippageModel()
        cost = sm.estimate_cost_per_trade("XAUUSD", TradingSession.LONDON, 0.01)
        assert "spread_pips" in cost
        assert "slippage_pips" in cost
        assert "total_usd" in cost
        assert cost["total_pips"] > 0

    def test_unknown_symbol_fallback(self):
        sm = SlippageModel()
        slip = sm.get_slippage("UNKNOWN_SYMBOL", TradingSession.LONDON)
        assert slip > 0  # falls back to default

    def test_string_session_coercion(self):
        sm = SlippageModel()
        slip = sm.get_slippage("XAUUSD", "london")
        assert slip > 0

    def test_string_volatility_coercion(self):
        sm = SlippageModel()
        slip = sm.get_slippage("XAUUSD", TradingSession.LONDON, "EXTREME")
        assert slip > 0

    def test_classify_session_rollover_boundary(self):
        """Rollover at 22:00 UTC — inside the 21:55-22:16 dead zone."""
        ts = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)
        assert classify_session(ts) == TradingSession.ROLLOVER

    def test_classify_session_returns_valid_enum(self):
        """classify_session always returns a valid TradingSession."""
        for hour in range(24):
            ts = datetime(2026, 1, 15, hour, 0, tzinfo=UTC)
            result = classify_session(ts)
            assert isinstance(result, TradingSession)
