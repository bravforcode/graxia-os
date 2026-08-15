"""Tests for core data models — edge cases, boundary conditions, serialization."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.enums import (
    CloseReason,
    DataQualityCheck,
    DecisionType,
    KillSwitchType,
    OrderStatus,
    RegimeType,
    SignalType,
    StrategyGroup,
    SystemState,
    TradingMode,
)
from graxia.packages.quant_os.core.enums import (
    RiskCheckResult as RiskCheckResultEnum,
)
from graxia.packages.quant_os.core.events import (
    BarEvent,
    Event,
    FillEvent,
    KillSwitchEvent,
    NewsEvent,
    OrderEvent,
    RegimeChangeEvent,
    RiskEvent,
    SignalEvent,
    TickEvent,
    TradeClosedEvent,
)
from graxia.packages.quant_os.core.exceptions import (
    BrokerError,
    CircuitBreakerError,
    ComplianceError,
    DataQualityError,
    DriftDetectedError,
    DuplicateOrderError,
    InsufficientEvidenceError,
    KillSwitchTriggeredError,
    MLModelError,
    OrderStateError,
    OverfittingError,
    PositionMismatchError,
    QuantException,
    RiskViolationError,
    StrategyError,
    StrictMTFViolation,
    ValidationError,
)
from graxia.packages.quant_os.risk.risk_policy import RiskPolicy

# ═══════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════


class TestEnums:
    """Edge cases for all system enums."""

    def test_system_state_completeness(self):
        assert len(SystemState) == 7
        values = [s.value for s in SystemState]
        assert "RESEARCH_ONLY" in values
        assert "LIVE_CONTROLLED" in values

    def test_order_status_has_all_terminal_states(self):
        terminal = {"FILLED", "REJECTED", "CANCELLED", "EXPIRED", "ERROR"}
        actual = {s.value for s in OrderStatus}
        assert terminal.issubset(actual)

    def test_regime_type_crisis_exists(self):
        assert RegimeType.CRISIS.value == "CRISIS"

    def test_signal_type_no_trade(self):
        assert SignalType.NO_TRADE.value == "NO_TRADE"

    def test_decision_type_abstain_variants(self):
        abstains = [d for d in DecisionType if d.value.startswith("ABSTAIN")]
        assert len(abstains) >= 4

    def test_kill_switch_type_data_quality(self):
        assert KillSwitchType.DATA_QUALITY.value == "DATA_QUALITY"

    def test_risk_check_result_fail_variants(self):
        fails = [r for r in RiskCheckResultEnum if r.value.startswith("FAIL_")]
        assert len(fails) >= 8

    def test_data_quality_check_stale(self):
        assert DataQualityCheck.STALE_QUOTE.value == "STALE_QUOTE"

    def test_strategy_group_ensemble(self):
        assert StrategyGroup.ENSEMBLE.value == "ENSEMBLE"

    def test_close_reason_circuit_breaker(self):
        assert CloseReason.CIRCUIT_BREAKER.value == "CIRCUIT_BREAKER"

    def test_order_status_str_comparison(self):
        assert OrderStatus.FILLED == "FILLED"
        assert OrderStatus.FILLED.value == "FILLED"


# ═══════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════


class TestExceptions:
    """Edge cases for exception hierarchy."""

    def test_base_quant_exception_defaults(self):
        exc = QuantException("test error")
        assert exc.message == "test error"
        assert exc.error_code == "QUANT_ERROR"
        assert exc.context == {}

    def test_base_quant_exception_with_context(self):
        ctx = {"key": "value", "nested": {"a": 1}}
        exc = QuantException("err", error_code="CODE_X", context=ctx)
        assert exc.error_code == "CODE_X"
        assert exc.context["nested"]["a"] == 1

    def test_risk_violation_inherits_quant(self):
        exc = RiskViolationError("risk too high", violation_type="MAX_POS")
        assert isinstance(exc, QuantException)
        assert exc.violation_type == "MAX_POS"
        assert exc.error_code == "RISK_VIOLATION"

    def test_compliance_error_default_check(self):
        exc = ComplianceError("compliance failed")
        assert exc.compliance_check == ""

    def test_kill_switch_error_inherits(self):
        exc = KillSwitchTriggeredError("halted", switch_type="DAILY_LOSS")
        assert exc.switch_type == "DAILY_LOSS"
        assert exc.error_code == "KILL_SWITCH"

    def test_data_quality_error_default_check(self):
        exc = DataQualityError("bad data")
        assert exc.check_type == ""

    def test_broker_error_default_broker(self):
        exc = BrokerError("connection failed")
        assert exc.broker == ""

    def test_overfitting_error_default_test(self):
        exc = OverfittingError("overfitting detected")
        assert exc.test_failed == ""

    def test_insufficient_evidence_default_list(self):
        exc = InsufficientEvidenceError("not enough evidence")
        assert exc.missing_evidence == []

    def test_insufficient_evidence_with_list(self):
        exc = InsufficientEvidenceError("missing data", missing_evidence=["sharpe", "sortino"])
        assert exc.missing_evidence == ["sharpe", "sortino"]

    def test_order_state_error_states(self):
        exc = OrderStateError("invalid transition", from_state="CREATED", to_state="FILLED")
        assert exc.from_state == "CREATED"
        assert exc.to_state == "FILLED"

    def test_duplicate_order_error_key(self):
        exc = DuplicateOrderError("dup", idempotency_key="abc123")
        assert exc.idempotency_key == "abc123"

    def test_position_mismatch_error_symbol(self):
        exc = PositionMismatchError("mismatch", symbol="EURUSD")
        assert exc.symbol == "EURUSD"

    def test_validation_error_field(self):
        exc = ValidationError("invalid", field="quantity")
        assert exc.field == "quantity"

    def test_strategy_error_id(self):
        exc = StrategyError("strategy failed", strategy_id="mtm_v2")
        assert exc.strategy_id == "mtm_v2"

    def test_ml_model_error_id(self):
        exc = MLModelError("model failed", model_id="xgb_v3")
        assert exc.model_id == "xgb_v3"

    def test_drift_detected_score(self):
        exc = DriftDetectedError("drift", model_id="rf_1", drift_score=0.42)
        assert exc.drift_score == 0.42

    def test_circuit_breaker_error_type(self):
        exc = CircuitBreakerError("tripped", breaker_type="metals")
        assert exc.breaker_type == "metals"

    def test_strict_mtf_violation_default_message(self):
        exc = StrictMTFViolation()
        assert "strict_mtf" in exc.message.lower()
        assert exc.error_code == "STRICT_MTF_VIOLATION"

    def test_exceptions_are_catchable_as_base(self):
        """All domain exceptions should be catchable as QuantException."""
        for exc_cls in [
            RiskViolationError,
            ComplianceError,
            KillSwitchTriggeredError,
            DataQualityError,
            BrokerError,
            OverfittingError,
            InsufficientEvidenceError,
            OrderStateError,
            DuplicateOrderError,
            PositionMismatchError,
            ValidationError,
            StrategyError,
            MLModelError,
            DriftDetectedError,
            CircuitBreakerError,
            StrictMTFViolation,
        ]:
            exc = exc_cls("test")
            assert isinstance(exc, QuantException)
            assert isinstance(exc, Exception)


# ═══════════════════════════════════════════════════════════════════════
# Events (frozen dataclasses)
# ═══════════════════════════════════════════════════════════════════════


class TestEvents:
    """Edge cases for event dataclasses."""

    def test_event_frozen(self):
        e = Event()
        with pytest.raises(FrozenInstanceError):
            e.source = "modified"

    def test_event_to_dict(self):
        e = Event(source="test_source")
        d = e.to_dict()
        assert d["source"] == "test_source"
        assert d["event_type"] == "Event"
        assert "event_id" in d
        assert "timestamp" in d

    def test_event_unique_ids(self):
        e1 = Event()
        e2 = Event()
        assert e1.event_id != e2.event_id

    def test_bar_event_defaults(self):
        b = BarEvent()
        assert b.timeframe == "M15"
        assert b.open == 0.0
        assert b.volume == 0.0

    def test_bar_event_frozen(self):
        b = BarEvent(symbol="XAUUSD", close=2350.0)
        with pytest.raises(FrozenInstanceError):
            b.close = 2400.0

    def test_bar_event_to_dict(self):
        b = BarEvent(symbol="EURUSD", open=1.08, high=1.09, low=1.07, close=1.085)
        d = b.to_dict()
        assert d["symbol"] == "EURUSD"
        assert d["event_type"] == "BarEvent"
        assert d["close"] == 1.085

    def test_tick_event_spread_validation(self):
        t = TickEvent(symbol="XAUUSD", bid=2024.50, ask=2025.00)
        assert t.ask > t.bid

    def test_signal_event_confidence_range(self):
        s = SignalEvent(symbol="EURUSD", confidence=0.85)
        assert 0.0 <= s.confidence <= 1.0

    def test_signal_event_regime_optional(self):
        s = SignalEvent(symbol="EURUSD")
        assert s.regime is None

    def test_signal_event_metadata_default_empty(self):
        s = SignalEvent(symbol="EURUSD")
        assert s.metadata == {}

    def test_order_event_zero_quantity(self):
        o = OrderEvent(quantity=0.0)
        assert o.quantity == 0.0

    def test_fill_event_commission_zero(self):
        f = FillEvent(commission=0.0, slippage=0.0)
        assert f.commission == 0.0

    def test_trade_closed_event_pnl_types(self):
        t = TradeClosedEvent(pnl=-50.0, pnl_pct=-2.5)
        assert t.pnl < 0
        assert t.pnl_pct < 0

    def test_risk_event_passed_default(self):
        r = RiskEvent()
        assert r.passed is True

    def test_kill_switch_event_severity(self):
        k = KillSwitchEvent(trigger="DAILY_LOSS", severity="P0")
        assert k.severity == "P0"

    def test_regime_change_event(self):
        r = RegimeChangeEvent(symbol="XAUUSD", old_regime="RANGE_BOUND", new_regime="CRISIS", confidence=0.95)
        assert r.new_regime == "CRISIS"

    def test_news_event_impact_values(self):
        for impact in ["LOW", "MEDIUM", "HIGH", "CRISIS"]:
            n = NewsEvent(headline="test", impact=impact)
            assert n.impact == impact

    def test_event_serialization_roundtrip(self):
        """Event to_dict should produce JSON-serializable output."""
        import json

        e = SignalEvent(symbol="EURUSD", signal_type=SignalType.BUY, confidence=0.75, metadata={"key": "value"})
        d = e.to_dict()
        serialized = json.dumps(d, default=str)
        assert "EURUSD" in serialized


# ═══════════════════════════════════════════════════════════════════════
# Risk Policy
# ═══════════════════════════════════════════════════════════════════════


class TestRiskPolicy:
    """Edge cases for RiskPolicy (bps-based)."""

    def test_default_values(self):
        rp = RiskPolicy()
        assert rp.risk_per_trade_bps == 100
        assert rp.max_daily_loss_bps == 50
        assert rp.max_weekly_loss_bps == 150
        assert rp.max_total_drawdown_bps == 300

    def test_risk_per_trade_fraction(self):
        rp = RiskPolicy(risk_per_trade_bps=10)
        assert rp.risk_per_trade_fraction == Decimal("10") / Decimal("10000")

    def test_max_daily_loss_fraction(self):
        rp = RiskPolicy(max_daily_loss_bps=50)
        assert rp.max_daily_loss_fraction == Decimal("50") / Decimal("10000")

    def test_max_weekly_loss_fraction(self):
        rp = RiskPolicy(max_weekly_loss_bps=150)
        assert rp.max_weekly_loss_fraction == Decimal("150") / Decimal("10000")

    def test_max_drawdown_fraction(self):
        rp = RiskPolicy(max_total_drawdown_bps=300)
        assert rp.max_total_drawdown_fraction == Decimal("300") / Decimal("10000")

    def test_risk_policy_frozen(self):
        rp = RiskPolicy()
        with pytest.raises(FrozenInstanceError):
            rp.risk_per_trade_bps = 20

    def test_zero_bps_values(self):
        rp = RiskPolicy(risk_per_trade_bps=0, max_daily_loss_bps=0)
        assert rp.risk_per_trade_fraction == Decimal("0")

    def test_max_positions_default(self):
        rp = RiskPolicy()
        assert rp.max_open_positions == 5

    def test_fail_closed_default(self):
        rp = RiskPolicy()
        assert rp.fail_closed is True

    def test_strict_mtf_default(self):
        rp = RiskPolicy()
        assert rp.strict_mtf is True


# ═══════════════════════════════════════════════════════════════════════
# Schemas (pandera validation)
# ═══════════════════════════════════════════════════════════════════════


class TestSchemas:
    """Edge cases for OHLCV schema validation."""

    def test_schema_exists(self):
        from graxia.packages.quant_os.core.schemas import XAUUSD_M15_SCHEMA

        assert XAUUSD_M15_SCHEMA is not None

    def test_validate_ohlcv_function_exists(self):
        from graxia.packages.quant_os.core.schemas import validate_ohlcv

        assert callable(validate_ohlcv)


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════


class TestConfig:
    """Edge cases for QuantConfig."""

    def test_config_enforces_hard_limits(self):
        from graxia.packages.quant_os.core.config import QuantConfig

        c = QuantConfig()
        assert c.max_risk_per_trade_pct <= 2.0
        assert c.max_drawdown_pct <= 25.0
        assert c.max_positions <= 20

    def test_config_paper_mode_no_live(self):
        from graxia.packages.quant_os.core.config import QuantConfig

        c = QuantConfig()
        assert c.trading_mode == TradingMode.PAPER
        assert c.live_trading_enabled is False

    def test_get_config_returns_singleton(self):
        from graxia.packages.quant_os.core.config import get_config, reset_config

        reset_config()
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2
        reset_config()

    def test_get_mode_risk_limits_paper(self):
        from graxia.packages.quant_os.core.config import QuantConfig

        c = QuantConfig()
        limits = c.get_mode_risk_limits()
        assert "max_risk_per_trade_pct" in limits
        assert limits["requires_human_confirm"] is False

    def test_get_mode_risk_limits_micro(self):
        import os

        from graxia.packages.quant_os.core.config import QuantConfig

        os.environ["TRADING_MODE"] = "LIVE_MICRO"
        try:
            c = QuantConfig()
            limits = c.get_mode_risk_limits()
            assert limits["requires_human_confirm"] is True
            assert limits["order_expiry_seconds"] == 60
        finally:
            os.environ.pop("TRADING_MODE", None)
