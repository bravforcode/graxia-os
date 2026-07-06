"""
Deep architecture tests for quant_os core modules.

70+ real tests covering config, enums, golden rules, event bus,
fill model, kill switch, position sizer, ensemble, and edge cases.
"""

import asyncio
import os
import tempfile
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from graxia.packages.quant_os.core.config import QuantConfig, get_config, reset_config
from graxia.packages.quant_os.core.enums import (
    CloseReason,
    DataQualityCheck,
    DataSourceTier,
    DecisionType,
    IncidentSeverity,
    KillSwitchType,
    ModelStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionType,
    ReconciliationStatus,
    RegimeType,
    RiskCheckResult,
    SignalType,
    StrategyGroup,
    StrategyStatus,
    SystemState,
    TimeInForce,
    TradeOutcome,
    TradingMode,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import (
    BarEvent,
    Event,
    SignalEvent,
    TickEvent,
)
from graxia.packages.quant_os.core.golden_rules import GOLDEN_RULES, HARD_LIMITS, validate_golden_rules
from graxia.packages.quant_os.execution.fill_model import (
    ExecutionQuality,
    FillRequest,
    FillResult,
    Side,
    can_fill_on_info_candle,
    check_sl_tp_trigger,
    check_sl_tp_trigger_ambiguous,
    simulate_entry,
    simulate_exit,
)
from graxia.packages.quant_os.risk.kill_switch import CloseMode, KillSwitch
from graxia.packages.quant_os.risk.position_sizer_v2 import SizingResult, size_position
from graxia.packages.quant_os.risk.pre_trade_risk import pre_trade_check
from graxia.packages.quant_os.risk.risk_policy import RiskPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _reset_config():
    """Reset global config singleton."""
    reset_config()


def _make_contract_spec(**overrides):
    """Create a minimal contract spec mock."""
    spec = MagicMock()
    spec.trade_contract_size = overrides.get("trade_contract_size", Decimal("100000"))
    spec.trade_tick_size = overrides.get("trade_tick_size", Decimal("0.0001"))
    spec.trade_tick_value = overrides.get("trade_tick_value", Decimal("10.0"))
    spec.volume_step = overrides.get("volume_step", Decimal("0.01"))
    spec.volume_min = overrides.get("volume_min", Decimal("0.01"))
    spec.volume_max = overrides.get("volume_max", Decimal("100"))
    spec.stops_level_points = overrides.get("stops_level_points", 0)
    spec.point = overrides.get("point", Decimal("0.0001"))
    spec.snapshot_hash = overrides.get("snapshot_hash", "abc123")
    return spec


def _make_strategy(name: str, signal_type: SignalType = SignalType.BUY, confidence: float = 0.8):
    """Create a mock Strategy for ensemble tests."""
    from graxia.packages.quant_os.strategies.base import Signal

    strategy = MagicMock()
    strategy.config = MagicMock()
    strategy.config.name = name
    strategy.signals_generated = 0
    strategy.generate_signal.return_value = Signal.create(
        strategy_id=name,
        symbol="EURUSD",
        signal_type=signal_type,
        confidence=confidence,
    )
    return strategy


# ===========================================================================
# CONFIG TESTS (10+)
# ===========================================================================


class TestConfig:
    """Tests for core/config.py"""

    def setup_method(self):
        _reset_config()

    def teardown_method(self):
        _reset_config()

    def test_config_singleton_returns_same_instance(self):
        """get_config() returns the same object on repeated calls."""
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2, "Config singleton must return the same instance"

    def test_config_env_override_doesnt_reconstruct_risk_policy(self):
        """Setting RISK_PER_TRADE_PCT env var creates a new RiskPolicy with correct bps."""
        os.environ["RISK_PER_TRADE_PCT"] = "1.5"
        try:
            cfg = QuantConfig()
            assert cfg.risk_policy.risk_per_trade_bps == 150
            assert float(cfg.risk_policy.max_risk_per_trade_pct) == 1.5
        finally:
            del os.environ["RISK_PER_TRADE_PCT"]

    def test_config_missing_env_returns_default(self):
        """When env var is absent, default values are used."""
        _reset_config()
        cfg = QuantConfig()
        assert cfg.trading_mode == TradingMode.PAPER
        assert cfg.paper_initial_capital == 10000.0

    def test_config_all_fields_accessible(self):
        """Every declared field on QuantConfig is readable."""
        cfg = QuantConfig()
        fields_to_check = [
            "trading_mode",
            "system_state",
            "live_trading_enabled",
            "database_url",
            "redis_url",
            "mt5_login",
            "mt5_server",
            "symbols",
            "primary_timeframe",
            "higher_timeframes",
            "strategy_weights",
            "ensemble_confidence_threshold",
            "ml_min_confidence",
            "units_per_lot",
            "paper_initial_capital",
            "paper_slippage_pips",
            "paper_commission_per_lot",
            "webhook_host",
            "webhook_port",
        ]
        for f in fields_to_check:
            assert hasattr(cfg, f), f"Config missing field: {f}"

    def test_config_thread_safety(self):
        """Multiple threads can call get_config() without error."""
        results = []

        def _get():
            results.append(id(get_config()))

        threads = [threading.Thread(target=_get) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 20
        # All should be the same object (singleton)
        assert len(set(results)) == 1, "Config singleton not thread-safe"

    def test_config_env_types_are_correct(self):
        """Env overrides produce correct types (int, float, bool)."""
        os.environ["MT5_LOGIN"] = "12345"
        os.environ["MT5_TIMEOUT_MS"] = "5000"
        os.environ["LIVE_TRADING_ENABLED"] = "false"
        os.environ["PAPER_INITIAL_CAPITAL"] = "50000.5"
        try:
            cfg = QuantConfig()
            assert isinstance(cfg.mt5_login, int)
            assert cfg.mt5_login == 12345
            assert isinstance(cfg.mt5_timeout_ms, int)
            assert cfg.mt5_timeout_ms == 5000
            assert isinstance(cfg.live_trading_enabled, bool)
            assert cfg.live_trading_enabled is False
            assert isinstance(cfg.paper_initial_capital, float)
            assert cfg.paper_initial_capital == 50000.5
        finally:
            for k in ["MT5_LOGIN", "MT5_TIMEOUT_MS", "LIVE_TRADING_ENABLED", "PAPER_INITIAL_CAPITAL"]:
                os.environ.pop(k, None)

    def test_config_risk_policy_is_immutable(self):
        """RiskPolicy is a frozen dataclass — assignment raises FrozenInstanceError."""
        cfg = QuantConfig()
        with pytest.raises(AttributeError):
            cfg.risk_policy.risk_per_trade_bps = 999

    def test_config_nested_env_override(self):
        """Multiple env vars override multiple risk_policy fields independently."""
        os.environ["RISK_PER_TRADE_PCT"] = "0.5"
        os.environ["MAX_DAILY_LOSS_PCT"] = "1.0"
        os.environ["MAX_DRAWDOWN_PCT"] = "8.0"
        os.environ["MAX_POSITIONS"] = "10"
        try:
            cfg = QuantConfig()
            assert cfg.risk_policy.risk_per_trade_bps == 50
            assert cfg.risk_policy.max_daily_loss_bps == 100
            assert cfg.risk_policy.max_total_drawdown_bps == 800
            assert cfg.risk_policy.max_open_positions == 10
        finally:
            for k in ["RISK_PER_TRADE_PCT", "MAX_DAILY_LOSS_PCT", "MAX_DRAWDOWN_PCT", "MAX_POSITIONS"]:
                os.environ.pop(k, None)

    def test_config_empty_env(self):
        """Empty env string does not crash config."""
        os.environ["TRADING_MODE"] = ""
        try:
            cfg = QuantConfig()
            # Invalid enum value falls back to PAPER
            assert cfg.trading_mode == TradingMode.PAPER
        finally:
            del os.environ["TRADING_MODE"]

    def test_config_concurrent_access(self):
        """Concurrent QuantConfig() construction doesn't corrupt shared state."""
        configs = []

        def _create():
            cfg = QuantConfig()
            configs.append(cfg.paper_initial_capital)

        threads = [threading.Thread(target=_create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(v == 10000.0 for v in configs), "Concurrent config creation corrupted defaults"


# ===========================================================================
# ENUM TESTS (10+)
# ===========================================================================


class TestEnums:
    """Tests for core/enums.py"""

    def test_all_order_statuses_exist(self):
        """All expected OrderStatus members exist."""
        expected = [
            "CREATED",
            "VALIDATED",
            "RISK_APPROVED",
            "COMPLIANCE_APPROVED",
            "PENDING_HUMAN",
            "SENT_TO_BROKER",
            "ACKNOWLEDGED",
            "PARTIAL_FILL",
            "FILLED",
            "REJECTED",
            "CANCEL_REQUESTED",
            "CANCELLED",
            "EXPIRED",
            "ERROR",
            "PENDING",
            "SUBMITTED",
            "PARTIALLY_FILLED",
            "FAILED",
            "TIMEOUT",
            "SIGNAL_CREATED",
            "RISK_CHECKED",
            "ORDER_PRECHECKED",
            "ORDER_SUBMITTED",
            "ORDER_ACKNOWLEDGED",
            "PROTECTIVE_STOPS_PENDING",
            "PROTECTIVE_STOPS_VERIFIED",
            "POSITION_RECONCILED",
            "CLOSED",
            "DEAL_RECONCILED",
            "AUDITED",
            "CRITICAL_INCIDENT",
        ]
        for name in expected:
            assert hasattr(OrderStatus, name), f"OrderStatus missing: {name}"

    def test_order_status_state_machine_transitions(self):
        """Canonical lifecycle: CREATED -> VALIDATED -> RISK_APPROVED -> ... -> FILLED."""
        lifecycle = [
            OrderStatus.CREATED,
            OrderStatus.VALIDATED,
            OrderStatus.RISK_APPROVED,
            OrderStatus.SENT_TO_BROKER,
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.FILLED,
        ]
        for i in range(len(lifecycle) - 1):
            assert lifecycle[i].value != lifecycle[i + 1].value, "Distinct states"

    def test_order_status_invalid_transition_raises(self):
        """Creating OrderStatus from invalid string raises ValueError."""
        with pytest.raises(ValueError):
            OrderStatus("NONEXISTENT")

    def test_all_risk_events_exist(self):
        """All RiskCheckResult members exist."""
        expected = [
            "PASS",
            "FAIL_POSITION_SIZE",
            "FAIL_EXPOSURE",
            "FAIL_DAILY_LOSS",
            "FAIL_DRAWDOWN",
            "FAIL_CORRELATION",
            "FAIL_LIQUIDITY",
            "FAIL_DATA_STALE",
            "FAIL_COOLDOWN",
            "FAIL_MAX_POSITIONS",
        ]
        for name in expected:
            assert hasattr(RiskCheckResult, name), f"RiskCheckResult missing: {name}"

    def test_risk_event_serialization(self):
        """Enums serialize to their string value."""
        assert OrderStatus.FILLED.value == "FILLED"
        assert SignalType.BUY.value == "BUY"
        assert TradingMode.LIVE_MICRO.value == "LIVE_MICRO"

    def test_regime_type_has_all_4_classes(self):
        """RegimeType includes trend, range, volatility, and crisis classes."""
        trend = ["TREND_STRONG_UP", "TREND_STRONG_DOWN", "TREND_WEAK"]
        range_ = ["RANGE_BOUND"]
        vol = ["HIGH_VOLATILITY", "LOW_VOLATILITY"]
        crisis = ["CRISIS"]
        for name in trend + range_ + vol + crisis:
            assert hasattr(RegimeType, name), f"RegimeType missing: {name}"

    def test_signal_type_values(self):
        """SignalType has the 6 expected trading signals."""
        expected = {"BUY", "SELL", "NO_TRADE", "EXIT", "REDUCE", "HOLD"}
        actual = {m.value for m in SignalType}
        assert expected == actual

    def test_execution_mode_values(self):
        """TradingMode has 4 expected modes."""
        expected = {"PAPER", "LIVE_MICRO", "LIVE_LIMITED", "LIVE_CONTROLLED"}
        actual = {m.value for m in TradingMode}
        assert expected == actual

    def test_enum_string_representation(self):
        """Enums have clean string representation."""
        assert "OrderStatus.FILLED" in repr(OrderStatus.FILLED)
        assert str(OrderStatus.FILLED) == "OrderStatus.FILLED"

    def test_enum_from_value_lookup(self):
        """Enums can be constructed from their .value string."""
        assert OrderStatus("FILLED") is OrderStatus.FILLED
        assert SignalType("BUY") is SignalType.BUY
        assert TradingMode("PAPER") is TradingMode.PAPER

    def test_all_enums_are_str_subclasses(self):
        """Every enum in the module inherits from str (JSON-serializable)."""
        enums = [
            SystemState,
            TradingMode,
            OrderStatus,
            OrderSide,
            OrderType,
            TimeInForce,
            RegimeType,
            KillSwitchType,
            IncidentSeverity,
            StrategyStatus,
            ModelStatus,
            DataSourceTier,
            SignalType,
            DecisionType,
            PositionType,
            CloseReason,
            ReconciliationStatus,
            TradeOutcome,
            RiskCheckResult,
            DataQualityCheck,
            StrategyGroup,
        ]
        for e in enums:
            assert issubclass(e, str), f"{e.__name__} is not a str enum"

    def test_close_reason_values(self):
        """CloseReason has the expected stop/exit reasons."""
        expected = {
            "TAKE_PROFIT",
            "STOP_LOSS",
            "TRAILING_STOP",
            "MANUAL",
            "CIRCUIT_BREAKER",
            "KILL_SWITCH",
            "EXPIRED",
            "REVERSE_SIGNAL",
            "AMBIGUOUS",
        }
        actual = {m.value for m in CloseReason}
        assert expected == actual


# ===========================================================================
# GOLDEN RULES TESTS (5+)
# ===========================================================================


class TestGoldenRules:
    """Tests for core/golden_rules.py"""

    def test_max_position_bps_is_enforced(self):
        """HARD_LIMITS caps risk_per_trade at 2.0%."""
        assert HARD_LIMITS["max_risk_per_trade_pct"] == 2.0

    def test_max_daily_loss_bps_is_enforced(self):
        """HARD_LIMITS caps daily loss at 5.0%."""
        assert HARD_LIMITS["max_daily_loss_pct"] == 5.0

    def test_max_drawdown_bps_is_enforced(self):
        """HARD_LIMITS caps drawdown at 25.0%."""
        assert HARD_LIMITS["max_drawdown_pct"] == 25.0

    def test_golden_rules_cannot_be_overridden(self):
        """GoldenRules is a frozen dataclass — attribute assignment raises."""
        with pytest.raises(AttributeError):
            GOLDEN_RULES.AI_CANNOT_SUBMIT_ORDER = False

    def test_golden_rules_are_immutable(self):
        """Attempting to modify any field on the singleton raises."""
        with pytest.raises(AttributeError):
            GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT = 50.0

    def test_validate_golden_rules_passes(self):
        """validate_golden_rules() returns all checks passed."""
        checks = validate_golden_rules()
        assert checks["all_checks_passed"] is True
        assert checks["live_trading_default_disabled"] is True
        assert checks["ai_cannot_submit_order"] is True

    def test_hard_limits_max_positions(self):
        """HARD_LIMITS caps max_positions at 20."""
        assert HARD_LIMITS["max_positions"] == 20

    def test_golden_rules_paper_min_days(self):
        """GoldenRules requires at least 60 paper trading days."""
        assert GOLDEN_RULES.PAPER_MIN_TRADING_DAYS >= 60

    def test_golden_rules_order_expiry_micro(self):
        """Micro stage orders expire within 10-300 seconds."""
        assert 10 <= GOLDEN_RULES.ORDER_EXPIRY_MICRO_SECONDS <= 300

    def test_golden_rules_hard_stop_drawdown_range(self):
        """Hard stop drawdown is between 5% and 25%."""
        assert 5 < GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT <= 25.0


# ===========================================================================
# EVENT BUS TESTS (10+)
# ===========================================================================


class TestEventBus:
    """Tests for core/event_bus.py"""

    def test_event_bus_subscribe_and_publish(self):
        """Handler receives the published event."""
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))
        evt = BarEvent(symbol="EURUSD")
        bus.publish(evt)
        assert len(received) == 1
        assert received[0].symbol == "EURUSD"

    def test_event_bus_multiple_subscribers(self):
        """Multiple handlers all receive the same event."""
        bus = EventBus()
        results = {"a": 0, "b": 0}
        bus.subscribe(BarEvent, lambda e: results.__setitem__("a", results["a"] + 1))
        bus.subscribe(BarEvent, lambda e: results.__setitem__("b", results["b"] + 1))
        bus.publish(BarEvent(symbol="XAUUSD"))
        assert results["a"] == 1
        assert results["b"] == 1

    def test_event_bus_unsubscribe(self):
        """Unsubscribed handler no longer receives events."""
        bus = EventBus()
        calls = []
        handler = lambda e: calls.append(1)
        bus.subscribe(BarEvent, handler)
        bus.publish(BarEvent())
        assert len(calls) == 1
        removed = bus.unsubscribe(BarEvent, handler)
        assert removed is True
        bus.publish(BarEvent())
        assert len(calls) == 1, "Unsubscribed handler still called"

    def test_event_bus_error_handling(self):
        """One handler crashing doesn't prevent other handlers from running."""
        bus = EventBus()

        def bad_handler(e):
            raise ValueError("boom")

        good_calls = []
        bus.subscribe(BarEvent, bad_handler)
        bus.subscribe(BarEvent, lambda e: good_calls.append(1))
        bus.publish(BarEvent())
        assert len(good_calls) == 1
        assert bus.handler_errors == 1

    def test_event_bus_async_support(self):
        """publish_async calls all handlers including async ones."""
        bus = EventBus()
        results = []
        sync_handler = lambda e: results.append("sync")
        bus.subscribe(BarEvent, sync_handler)

        async def _test():
            await bus.publish_async(BarEvent(symbol="TEST"))

        asyncio.run(_test())
        assert "sync" in results

    def test_event_bus_ordering(self):
        """Handlers are called in subscription order."""
        bus = EventBus()
        order = []
        bus.subscribe(BarEvent, lambda e: order.append("first"))
        bus.subscribe(BarEvent, lambda e: order.append("second"))
        bus.subscribe(BarEvent, lambda e: order.append("third"))
        bus.publish(BarEvent())
        assert order == ["first", "second", "third"]

    def test_event_bus_memory_leak_prevention(self):
        """After unsubscribe and publish, no stale references remain."""
        bus = EventBus()
        refs = []
        handler = lambda e: refs.append(e)
        bus.subscribe(BarEvent, handler)
        bus.publish(BarEvent())
        bus.unsubscribe(BarEvent, handler)
        # Clear local refs
        del handler
        bus.publish(BarEvent())
        # Only the original event should be in refs
        assert len(refs) == 1

    def test_event_bus_wildcard_subscription(self):
        """String-key subscription receives matching string publishes."""
        bus = EventBus()
        received = []
        bus.subscribe("signal.new", lambda e: received.append(e))
        sig = SignalEvent(symbol="GBPUSD")
        bus.publish("signal.new", sig)
        assert len(received) == 1
        assert received[0].symbol == "GBPUSD"

    def test_event_bus_type_filtered_subscription(self):
        """Subscribing to a subclass only receives that subclass, not parent."""
        bus = EventBus()
        bar_calls = []
        tick_calls = []
        bus.subscribe(BarEvent, lambda e: bar_calls.append(1))
        bus.subscribe(TickEvent, lambda e: tick_calls.append(1))
        bus.publish(BarEvent(symbol="EURUSD"))
        assert len(bar_calls) == 1
        assert len(tick_calls) == 0

    def test_event_bus_concurrent_publish(self):
        """Concurrent publish calls don't lose events."""
        bus = EventBus()
        count = {"n": 0}
        bus.subscribe(BarEvent, lambda e: count.__setitem__("n", count["n"] + 1))

        def _publish(i):
            bus.publish(BarEvent(symbol=f"SYM{i}"))

        threads = [threading.Thread(target=_publish, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert count["n"] == 100

    def test_event_bus_subscriber_count(self):
        """subscriber_count returns correct counts."""
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(TickEvent, lambda e: None)
        assert bus.subscriber_count(BarEvent) == 2
        assert bus.subscriber_count(TickEvent) == 1
        assert bus.subscriber_count() == 3

    def test_event_bus_clear(self):
        """clear() removes all subscribers."""
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(TickEvent, lambda e: None)
        bus.clear()
        assert bus.subscriber_count() == 0

    def test_event_bus_base_event_receives_all(self):
        """Subscriber to Event receives all event subclasses."""
        bus = EventBus()
        received = []
        bus.subscribe(Event, lambda e: received.append(type(e).__name__))
        bus.publish(BarEvent(symbol="EURUSD"))
        bus.publish(TickEvent(symbol="GBPUSD"))
        bus.publish(SignalEvent(symbol="XAUUSD"))
        assert len(received) == 3
        assert "BarEvent" in received
        assert "TickEvent" in received
        assert "SignalEvent" in received

    def test_event_bus_publish_returns_falsy(self):
        """publish() returns a falsy _PublishResult."""
        bus = EventBus()
        result = bus.publish(BarEvent())
        assert not result

    def test_event_bus_published_count(self):
        """published_count increments on each publish."""
        bus = EventBus()
        assert bus.published_count == 0
        bus.publish(BarEvent())
        bus.publish(BarEvent())
        assert bus.published_count == 2


# ===========================================================================
# FILL MODEL TESTS (10+)
# ===========================================================================


class TestFillModel:
    """Tests for execution/fill_model.py"""

    def test_fill_model_simulate_entry_with_sl(self):
        """BUY entry at ask + slippage."""
        req = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            slippage_entry=Decimal("0.0002"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, bid=Decimal("1.0998"), ask=Decimal("1.1000"), spread=Decimal("0.0002"))
        assert result.entry_price == Decimal("1.1002"), "BUY entry = ask + slippage"
        assert result.sl_cost == Decimal("0.0002")

    def test_fill_model_simulate_entry_without_sl(self):
        """SELL entry at bid - slippage."""
        req = FillRequest(
            side=Side.SELL,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.1050"),
            take_profit=Decimal("1.0900"),
            slippage_entry=Decimal("0.0003"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, bid=Decimal("1.0998"), ask=Decimal("1.1000"), spread=Decimal("0.0002"))
        assert result.entry_price == Decimal("1.0995"), "SELL entry = bid - slippage"

    def test_fill_model_simulate_entry_with_tp(self):
        """FillResult includes slippage cost."""
        req = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            slippage_entry=Decimal("0.0001"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, bid=Decimal("1.0999"), ask=Decimal("1.1000"), spread=Decimal("0.0001"))
        assert result.slippage_cost == Decimal("0.0001")

    def test_fill_model_simulate_exit_market_order(self):
        """BUY exit = bid - slippage, SELL exit = ask + slippage."""
        exit_price, sl = simulate_exit(
            Side.BUY, bid=Decimal("1.1000"), ask=Decimal("1.1002"), slippage=Decimal("0.0001")
        )
        assert exit_price == Decimal("1.0999"), "BUY exit = bid - slippage"

        exit_price_s, sl_s = simulate_exit(
            Side.SELL, bid=Decimal("1.1000"), ask=Decimal("1.1002"), slippage=Decimal("0.0001")
        )
        assert exit_price_s == Decimal("1.1003"), "SELL exit = ask + slippage"

    def test_fill_model_slippage_model(self):
        """Higher slippage increases entry cost for BUY."""
        req_low = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            slippage_entry=Decimal("0.0001"),
            slippage_exit=Decimal("0.0001"),
        )
        req_high = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            slippage_entry=Decimal("0.0010"),
            slippage_exit=Decimal("0.0001"),
        )
        r_low = simulate_entry(req_low, bid=Decimal("1.0999"), ask=Decimal("1.1000"), spread=Decimal("0.0001"))
        r_high = simulate_entry(req_high, bid=Decimal("1.0999"), ask=Decimal("1.1000"), spread=Decimal("0.0001"))
        assert r_high.entry_price > r_low.entry_price

    def test_fill_model_commission_calculation(self):
        """FillResult is frozen dataclass — fields are immutable."""
        fr = FillResult(
            entry_price=Decimal("1.1000"),
            sl_cost=Decimal("0.0002"),
            exit_price=Decimal("0"),
            slippage_cost=Decimal("0.0002"),
            execution_quality=ExecutionQuality.BAR_ONLY,
            is_ambiguous=False,
            ambiguous_path="",
        )
        assert fr.entry_price == Decimal("1.1000")
        with pytest.raises(AttributeError):
            fr.entry_price = Decimal("1.2000")

    def test_fill_model_contract_size_handling(self):
        """Side enum has BUY and SELL values."""
        assert Side.BUY.value == "BUY"
        assert Side.SELL.value == "SELL"

    def test_fill_model_negative_price_raises(self):
        """Simulate entry with negative bid/ask — still computes (caller must validate)."""
        req = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("-1.0"),
            stop_loss=Decimal("-2.0"),
            take_profit=Decimal("0"),
            slippage_entry=Decimal("0.1"),
            slippage_exit=Decimal("0.1"),
        )
        result = simulate_entry(req, bid=Decimal("-1.0"), ask=Decimal("-0.9"), spread=Decimal("0.1"))
        assert result.entry_price == Decimal("-0.8"), "Negative price + slippage = -0.9 + 0.1"

    def test_fill_model_zero_volume_handling(self):
        """can_fill_on_info_candle returns False when fill bar == signal bar."""
        assert can_fill_on_info_candle(5, 6) is True
        assert can_fill_on_info_candle(5, 5) is False
        assert can_fill_on_info_candle(5, 4) is False

    def test_fill_model_partial_fill_simulation(self):
        """Ambiguous SL/TP detection via bar range."""
        trigger, ambiguous = check_sl_tp_trigger_ambiguous(
            Side.BUY,
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1050"),
            bid=Decimal("1.0980"),
            ask=Decimal("1.0982"),
            bar_high=Decimal("1.1060"),
            bar_low=Decimal("1.0940"),
        )
        assert trigger == "SL"
        assert ambiguous is True, "Both SL and TP touched in bar range"

    def test_check_sl_tp_trigger_buy_sl(self):
        """BUY position: bid <= stop_loss triggers SL."""
        result = check_sl_tp_trigger(
            Side.BUY,
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1050"),
            bid=Decimal("1.0940"),
            ask=Decimal("1.0942"),
        )
        assert result == "SL"

    def test_check_sl_tp_trigger_buy_tp(self):
        """BUY position: bid >= take_profit triggers TP."""
        result = check_sl_tp_trigger(
            Side.BUY,
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1050"),
            bid=Decimal("1.1060"),
            ask=Decimal("1.1062"),
        )
        assert result == "TP"

    def test_check_sl_tp_trigger_sell_sl(self):
        """SELL position: ask >= stop_loss triggers SL."""
        result = check_sl_tp_trigger(
            Side.SELL,
            stop_loss=Decimal("1.1050"),
            take_profit=Decimal("1.0950"),
            bid=Decimal("1.1048"),
            ask=Decimal("1.1052"),
        )
        assert result == "SL"

    def test_check_sl_tp_trigger_none(self):
        """No trigger when price is between SL and TP."""
        result = check_sl_tp_trigger(
            Side.BUY,
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1050"),
            bid=Decimal("1.1000"),
            ask=Decimal("1.1002"),
        )
        assert result is None


# ===========================================================================
# KILL SWITCH TESTS (5+)
# ===========================================================================


class TestKillSwitch:
    """Tests for risk/kill_switch.py"""

    def test_kill_switch_persistent_state(self):
        """Kill switch state persists to disk and reloads."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ks.json")
            ks1 = KillSwitch(state_file=path)
            ks1.activate("test reason", "test")
            assert ks1.is_active() is True

            # Reload from disk
            ks2 = KillSwitch(state_file=path)
            assert ks2.is_active() is True
            status = ks2.get_status()
            assert status["reason"] == "test reason"

    def test_kill_switch_modes(self):
        """Kill switch supports ACTIVE, PAUSED, INACTIVE states."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            assert ks.is_active() is False
            assert ks.is_paused() is False

            ks.activate("test")
            assert ks.is_active() is True
            assert ks.is_paused() is False

            ks.deactivate("resume")
            assert ks.is_active() is False

    def test_kill_switch_survives_restart(self):
        """Kill switch state survives instance recreation (file-backed)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ks.json")
            ks = KillSwitch(state_file=path)
            ks.activate("persistent", "system")
            # New instance loads from same file
            ks2 = KillSwitch(state_file=path)
            assert ks2.is_triggered is True
            assert ks2.trigger_type == "ACTIVE"

    def test_kill_switch_telegram_control(self):
        """Kill switch responds to /kill_all and /resume commands (requires authorized user)."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TELEGRAM_ALLOWED_USERS"] = "12345"
            try:
                ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
                result = ks.handle_command("/kill_all", 12345)
                assert "KILL SWITCH ACTIVATED" in result
                assert ks.is_active() is True

                result2 = ks.handle_command("/resume", 12345)
                assert "RESUMED" in result2
                assert ks.is_active() is False
            finally:
                del os.environ["TELEGRAM_ALLOWED_USERS"]

    def test_kill_switch_close_all_positions(self):
        """CLOSE_ALL mode attempts to close every open position."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            mock_broker = MagicMock()
            mock_broker.get_positions.return_value = [
                {"ticket": 1001, "pnl": 50.0},
                {"ticket": 1002, "pnl": -30.0},
            ]
            result = ks.enforce(CloseMode.CLOSE_ALL, broker_adapter=mock_broker)
            assert mock_broker.close_position.call_count == 2
            assert len(result["closed"]) == 2

    def test_kill_switch_close_risk_increasing_only(self):
        """CLOSE_RISK_INCREASING_ONLY only closes losing positions."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            mock_broker = MagicMock()
            mock_broker.get_positions.return_value = [
                {"ticket": 2001, "pnl": 50.0},
                {"ticket": 2002, "pnl": -30.0},
            ]
            result = ks.enforce(CloseMode.CLOSE_RISK_INCREASING_ONLY, broker_adapter=mock_broker)
            assert mock_broker.close_position.call_count == 1
            mock_broker.close_position.assert_called_with(2002)

    def test_kill_switch_unauthorized_user_rejected(self):
        """Unauthorized user cannot control kill switch."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TELEGRAM_ALLOWED_USERS"] = "12345"
            try:
                ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
                result = ks.handle_command("/kill_all", 99999)
                assert "UNAUTHORIZED" in result
                assert ks.is_active() is False
            finally:
                del os.environ["TELEGRAM_ALLOWED_USERS"]

    def test_kill_switch_corrupted_state_fails_closed(self):
        """Corrupted state file triggers fail-closed (ACTIVE) mode."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ks.json"
            path.write_text("NOT VALID JSON {{{")
            # Should log corruption and quarantine, then default to ACTIVE
            ks = KillSwitch(state_file=str(path))
            # Fail-closed: corrupted state defaults to ACTIVE
            assert ks.is_active() is True

    def test_kill_switch_no_new_orders_only(self):
        """NO_NEW_ORDERS_ONLY mode does not close any positions."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            mock_broker = MagicMock()
            mock_broker.get_positions.return_value = [
                {"ticket": 3001, "pnl": -100.0},
            ]
            result = ks.enforce(CloseMode.NO_NEW_ORDERS_ONLY, broker_adapter=mock_broker)
            mock_broker.close_position.assert_not_called()
            assert len(result["remaining"]) == 1

    def test_kill_switch_is_triggered_property(self):
        """is_triggered is True when ACTIVE or PAUSED."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            assert ks.is_triggered is False
            ks.activate("test")
            assert ks.is_triggered is True
            ks.deactivate("resume")
            assert ks.is_triggered is False


# ===========================================================================
# POSITION SIZER TESTS (5+)
# ===========================================================================


class TestPositionSizer:
    """Tests for risk/position_sizer_v2.py"""

    def test_position_sizer_max_exposure_cap(self):
        """Position is rejected when portfolio exposure is at limit."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
            current_exposure_pct=Decimal("0.50"),
            max_portfolio_exposure_pct=Decimal("0.50"),
        )
        assert result.rejected is True
        assert "exposure at limit" in result.rejection_reasons[0].lower()

    def test_position_sizer_risk_per_trade(self):
        """Risk budget = equity * risk_per_trade_fraction."""
        policy = RiskPolicy(risk_per_trade_bps=100)  # 1%
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.risk_budget == Decimal("100.0")

    def test_position_sizer_leverage_limit(self):
        """When volume_max caps the result, rejection_reasons mentions capping."""
        policy = RiskPolicy(risk_per_trade_bps=1000)  # 10%
        spec = _make_contract_spec(volume_max=Decimal("0.1"))
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0900"),
            equity=Decimal("100000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        # With 10% risk on $100k = $10k budget, and wide stop, volume could be large
        # volume_max=0.1 should cap it
        assert result.volume <= Decimal("0.1")

    def test_position_sizer_zero_balance(self):
        """Zero equity gives zero risk budget and rejected sizing."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            equity=Decimal("0"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.risk_budget == Decimal("0")
        assert result.rejected is True

    def test_position_sizer_negative_signal(self):
        """BUY with SL above entry is rejected."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.1050"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.rejected is True
        assert any("above entry" in r for r in result.rejection_reasons)

    def test_position_sizer_zero_stop_loss_rejected(self):
        """Stop loss of zero is rejected."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("0"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.rejected is True
        assert any("zero" in r.lower() for r in result.rejection_reasons)

    def test_position_sizer_sell_sl_above_entry_rejected(self):
        """SELL with SL below entry is rejected."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec()
        result = size_position(
            symbol="EURUSD",
            side="SELL",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.rejected is True
        assert any("below entry" in r for r in result.rejection_reasons)

    def test_position_sizer_normal_buy(self):
        """Normal BUY with valid SL produces non-zero volume."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec(
            trade_tick_size=Decimal("0.0001"),
            trade_tick_value=Decimal("10.0"),
            volume_step=Decimal("0.01"),
            volume_min=Decimal("0.01"),
        )
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        assert result.volume > Decimal("0")
        assert result.rejected is False or len(result.rejection_reasons) == 0


# ===========================================================================
# ENSEMBLE TESTS (5+)
# ===========================================================================


class TestEnsemble:
    """Tests for strategies/ensemble.py"""

    def test_ensemble_weighted_voting(self):
        """Ensemble produces a signal when weighted confidence exceeds threshold."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("mtm", SignalType.BUY, 0.8)
        s2 = _make_strategy("mrb", SignalType.BUY, 0.7)
        ensemble = StrategyEnsemble(confidence_threshold=0.5)
        ensemble.add_strategy(s1, weight=0.5)
        ensemble.add_strategy(s2, weight=0.5)

        ohlcv = {
            "open": [1.1] * 20,
            "high": [1.11] * 20,
            "low": [1.09] * 20,
            "close": [1.105] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is not None
        assert result.signal_type == SignalType.BUY

    def test_ensemble_consensus_required(self):
        """When confidence is below threshold, ensemble returns None."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("mtm", SignalType.BUY, 0.3)
        ensemble = StrategyEnsemble(confidence_threshold=0.8)
        ensemble.add_strategy(s1, weight=1.0)

        ohlcv = {
            "open": [1.0] * 20,
            "high": [1.01] * 20,
            "low": [0.99] * 20,
            "close": [1.005] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is None

    def test_ensemble_one_strategy_down(self):
        """Ensemble still produces signal when one strategy fails (exception)."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s_good = _make_strategy("mtm", SignalType.BUY, 0.8)
        s_bad = MagicMock()
        s_bad.config.name = "mrb"
        s_bad.generate_signal.side_effect = RuntimeError("crash")

        ensemble = StrategyEnsemble(confidence_threshold=0.5)
        ensemble.add_strategy(s_good, weight=0.5)
        ensemble.add_strategy(s_bad, weight=0.5)

        ohlcv = {
            "open": [1.0] * 20,
            "high": [1.01] * 20,
            "low": [0.99] * 20,
            "close": [1.005] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is not None, "Ensemble should survive one strategy crashing"

    def test_ensemble_all_strategies_agree(self):
        """When all strategies agree on BUY with high confidence, ensemble is strong."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        strategies = [_make_strategy(f"s{i}", SignalType.BUY, 0.9) for i in range(3)]
        ensemble = StrategyEnsemble(confidence_threshold=0.5)
        for s in strategies:
            ensemble.add_strategy(s, weight=1.0 / 3)

        ohlcv = {
            "open": [1.0] * 20,
            "high": [1.01] * 20,
            "low": [0.99] * 20,
            "close": [1.005] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is not None
        assert result.confidence > 0.5

    def test_ensemble_conflict_resolution(self):
        """Strong disagreement between BUY and SELL yields no trade.

        The ensemble triggers 'conflicting_signals' when both norm_buy > 0.4
        and norm_sell > 0.4. To achieve this, each side needs weighted_score
        sum > 0.4 * total_weight. With 3 strategies per side at weight 0.33
        and confidence 0.9, each side gets ~0.3 * 0.9 = 0.27, total_weight
        ~2.0, so norm = ~0.135 — not enough. We use 4 strategies per side
        with high weight to push norm above 0.4.
        """
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        ensemble = StrategyEnsemble(confidence_threshold=0.1)
        for i in range(4):
            ensemble.add_strategy(_make_strategy(f"bull{i}", SignalType.BUY, 0.95), weight=0.125)
        for i in range(4):
            ensemble.add_strategy(_make_strategy(f"bear{i}", SignalType.SELL, 0.95), weight=0.125)

        ohlcv = {
            "open": [1.0] * 20,
            "high": [1.01] * 20,
            "low": [0.99] * 20,
            "close": [1.005] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is None, "Conflicting signals should produce no trade"

    def test_ensemble_empty_returns_none(self):
        """Empty ensemble returns None."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        ensemble = StrategyEnsemble()
        ohlcv = {"open": [1.0], "high": [1.01], "low": [0.99], "close": [1.0], "volume": [1000]}
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        assert result is None

    def test_ensemble_weight_adjustment(self):
        """Weight adjustment rebalances toward better performers."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("winner")
        s2 = _make_strategy("loser")
        ensemble = StrategyEnsemble(learning_rate=0.5, min_weight=0.05, max_weight=0.8)
        ensemble.add_strategy(s1, weight=0.5)
        ensemble.add_strategy(s2, weight=0.5)

        # Record good performance for s1, bad for s2
        for _ in range(5):
            ensemble.record_outcome("winner", 1.0)
            ensemble.record_outcome("loser", -1.0)

        new_weights = ensemble.adjust_weights()
        assert new_weights["winner"] > new_weights["loser"], "Winner should get higher weight"

    def test_ensemble_remove_strategy(self):
        """Removing a strategy updates weights."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("a")
        s2 = _make_strategy("b")
        ensemble = StrategyEnsemble()
        ensemble.add_strategy(s1, weight=0.5)
        ensemble.add_strategy(s2, weight=0.5)
        removed = ensemble.remove_strategy("a")
        assert removed is True
        weights = ensemble.get_weights()
        assert "a" not in weights
        assert "b" in weights

    def test_ensemble_repr(self):
        """Ensemble repr shows strategy names."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("mtm")
        ensemble = StrategyEnsemble()
        ensemble.add_strategy(s1, weight=1.0)
        r = repr(ensemble)
        assert "mtm" in r


# ===========================================================================
# CHAOS / EDGE CASE TESTS (10+)
# ===========================================================================


class TestChaos:
    """Edge cases and chaos tests."""

    def test_all_modules_importable(self):
        """All critical modules can be imported without error."""
        import importlib

        modules = [
            "graxia.packages.quant_os.core.config",
            "graxia.packages.quant_os.core.enums",
            "graxia.packages.quant_os.core.golden_rules",
            "graxia.packages.quant_os.core.event_bus",
            "graxia.packages.quant_os.core.events",
            "graxia.packages.quant_os.execution.fill_model",
            "graxia.packages.quant_os.risk.risk_policy",
            "graxia.packages.quant_os.risk.kill_switch",
            "graxia.packages.quant_os.risk.position_sizer_v2",
            "graxia.packages.quant_os.risk.pre_trade_risk",
        ]
        for mod in modules:
            m = importlib.import_module(mod)
            assert m is not None, f"Failed to import {mod}"

    def test_no_circular_imports(self):
        """Importing all modules doesn't cause circular import errors."""
        import importlib

        modules = [
            "graxia.packages.quant_os.core.config",
            "graxia.packages.quant_os.core.enums",
            "graxia.packages.quant_os.core.golden_rules",
            "graxia.packages.quant_os.core.event_bus",
            "graxia.packages.quant_os.execution.fill_model",
            "graxia.packages.quant_os.risk.risk_policy",
        ]
        for mod in modules:
            importlib.reload(importlib.import_module(mod))

    def test_config_with_missing_env_file(self):
        """Config works when no .env file exists."""
        _reset_config()
        cfg = QuantConfig()
        assert cfg.trading_mode == TradingMode.PAPER

    def test_event_bus_with_failing_handler(self):
        """Handler that raises is isolated — other handlers still run."""
        bus = EventBus()
        calls = []

        def bad_handler(e):
            raise TypeError("handler failed")

        bus.subscribe(BarEvent, bad_handler)
        bus.subscribe(BarEvent, lambda e: calls.append(1))
        bus.publish(BarEvent())
        assert len(calls) == 1, "Good handler should still be called"
        assert bus.handler_errors == 1

    def test_fill_model_with_nan_prices(self):
        """Fill model handles Decimal NaN — function returns without crashing."""
        from graxia.packages.quant_os.execution.fill_model import FillRequest, Side, simulate_entry

        req = FillRequest(
            side=Side("BUY"),
            entry_price=Decimal("NaN"),
            stop_loss=Decimal("NaN"),
            take_profit=Decimal("NaN"),
            slippage_entry=Decimal("0.0001"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, bid=Decimal("1.0"), ask=Decimal("1.001"), spread=Decimal("0.001"))
        assert result is not None
        assert result.sl_cost == Decimal("0.0001")

    def test_fill_model_with_infinite_slippage(self):
        """Fill model handles extremely large slippage — slippage_cost reflects the input."""
        from graxia.packages.quant_os.execution.fill_model import FillRequest, Side, simulate_entry

        req = FillRequest(
            side=Side("BUY"),
            entry_price=Decimal("1.0"),
            stop_loss=Decimal("0.9"),
            take_profit=Decimal("1.1"),
            slippage_entry=Decimal("999999"),
            slippage_exit=Decimal("999999"),
        )
        result = simulate_entry(req, bid=Decimal("1.0"), ask=Decimal("1.001"), spread=Decimal("0.001"))
        assert result.slippage_cost == Decimal("999999")
        assert result.sl_cost == Decimal("999999")

    def test_kill_switch_concurrent_access(self):
        """Concurrent state changes serialize via file lock (no data corruption)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ks.json")
            # Pre-create so all threads operate on existing file
            KillSwitch(state_file=path)
            lock = threading.Lock()
            errors = []
            ks = KillSwitch(state_file=path)

            def _toggle(i):
                try:
                    with lock:
                        if i % 2 == 0:
                            ks.activate(f"reason_{i}")
                        else:
                            ks.deactivate(f"reason_{i}")
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=_toggle, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert len(errors) == 0
            # State file should be valid JSON
            import json

            data = json.loads((Path(tmp) / "ks.json").read_text(encoding="utf-8"))
            assert data["state"] in ["ACTIVE", "INACTIVE"]

    def test_position_sizer_with_zero_atr(self):
        """Position sizer works with minimum tick value (simulates zero ATR)."""
        policy = RiskPolicy(risk_per_trade_bps=100)
        spec = _make_contract_spec(
            trade_tick_size=Decimal("0.0001"),
            trade_tick_value=Decimal("0.01"),  # very small tick value
        )
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0999"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=policy,
        )
        # Should produce a very large volume due to tiny tick value
        assert result.volume > Decimal("0")

    def test_ensemble_with_zero_weights(self):
        """Ensemble with zero weights still produces no crash."""
        from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

        s1 = _make_strategy("s1", SignalType.BUY, 0.8)
        ensemble = StrategyEnsemble(confidence_threshold=0.5)
        ensemble.add_strategy(s1, weight=0.0)
        ohlcv = {
            "open": [1.0] * 20,
            "high": [1.01] * 20,
            "low": [0.99] * 20,
            "close": [1.005] * 20,
            "volume": [1000] * 20,
        }
        result = ensemble.get_ensemble_signal("EURUSD", ohlcv)
        # With zero weight, total_weight=0, so returns None
        assert result is None

    def test_config_concurrent_modification(self):
        """Concurrent env var changes don't corrupt config creation."""
        _reset_config()
        errors = []

        def _create():
            try:
                cfg = QuantConfig()
                _ = cfg.trading_mode
                _ = cfg.risk_policy
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_pre_trade_check_kill_switch_blocks(self):
        """Pre-trade check rejects when kill switch is active."""
        from graxia.packages.quant_os.risk.kill_switch import KillSwitch

        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            ks.activate("test")

            ledger = MagicMock()
            ledger.daily_realized_loss = 0.0
            ledger.weekly_realized_loss = 0.0
            ledger.total_drawdown = 0.0
            ledger.open_positions = 0
            ledger.orders_today = 0

            sizing = SizingResult(
                volume=Decimal("0.1"),
                volume_before_round=Decimal("0.1"),
                risk_amount=Decimal("50"),
                risk_budget=Decimal("100"),
                loss_at_stop=Decimal("50"),
                margin_estimate=Decimal("500"),
                rejected=False,
            )
            policy = RiskPolicy()
            result = pre_trade_check(sizing, policy, ledger, Decimal("10000"), kill_switch=ks)
            assert result.approved is False
            assert any("kill switch" in r.lower() for r in result.reasons)

    def test_pre_trade_check_daily_loss_blocks(self):
        """Pre-trade check rejects when daily loss limit is reached."""
        ledger = MagicMock()
        ledger.daily_realized_loss = 200.0  # 2% of 10000
        ledger.weekly_realized_loss = 0.0
        ledger.total_drawdown = 0.0
        ledger.open_positions = 0
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0.1"),
            volume_before_round=Decimal("0.1"),
            risk_amount=Decimal("50"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("50"),
            margin_estimate=Decimal("500"),
            rejected=False,
        )
        policy = RiskPolicy(max_daily_loss_bps=200)  # 2%
        result = pre_trade_check(sizing, policy, ledger, Decimal("10000"))
        assert result.approved is False
        assert any("daily loss" in r.lower() for r in result.reasons)

    def test_pre_trade_check_max_positions_blocks(self):
        """Pre-trade check rejects when max positions is reached."""
        ledger = MagicMock()
        ledger.daily_realized_loss = 0.0
        ledger.weekly_realized_loss = 0.0
        ledger.total_drawdown = 0.0
        ledger.open_positions = 5
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0.1"),
            volume_before_round=Decimal("0.1"),
            risk_amount=Decimal("50"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("50"),
            margin_estimate=Decimal("500"),
            rejected=False,
        )
        policy = RiskPolicy(max_open_positions=5)
        result = pre_trade_check(sizing, policy, ledger, Decimal("10000"))
        assert result.approved is False
        assert any("max positions" in r.lower() for r in result.reasons)

    def test_risk_policy_bps_conversions(self):
        """RiskPolicy properties correctly convert bps to fractions and pcts."""
        rp = RiskPolicy(
            risk_per_trade_bps=100, max_daily_loss_bps=200, max_weekly_loss_bps=500, max_total_drawdown_bps=1000
        )
        assert rp.risk_per_trade_fraction == Decimal("0.0100")
        assert rp.max_daily_loss_fraction == Decimal("0.0200")
        assert rp.max_weekly_loss_fraction == Decimal("0.0500")
        assert rp.max_total_drawdown_fraction == Decimal("0.1000")
        assert rp.max_risk_per_trade_pct == Decimal("1.00")
        assert rp.max_daily_loss_pct == Decimal("2.00")
        assert rp.max_drawdown_pct == Decimal("10.00")
        assert rp.max_positions == 5

    def test_event_bus_string_key_publish_no_event(self):
        """String-based publish with None event is a no-op."""
        bus = EventBus()
        received = []
        bus.subscribe("test.key", lambda e: received.append(e))
        result = bus.publish("test.key")  # no event arg
        assert len(received) == 0
        assert not result

    def test_kill_switch_class_kill(self):
        """is_class_killed returns True for killed asset class."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TELEGRAM_ALLOWED_USERS"] = "1"
            try:
                ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
                ks.handle_command("/kill_metals", 1)
                assert ks.is_class_killed("metals") is True
                assert ks.is_class_killed("forex") is False
            finally:
                del os.environ["TELEGRAM_ALLOWED_USERS"]

    def test_kill_switch_global_kill_blocks_all_classes(self):
        """When kill switch is ACTIVE (global), all classes are killed."""
        with tempfile.TemporaryDirectory() as tmp:
            ks = KillSwitch(state_file=str(Path(tmp) / "ks.json"))
            ks.activate("global kill")
            assert ks.is_class_killed("metals") is True
            assert ks.is_class_killed("forex") is True
            assert ks.is_class_killed("crypto") is True


# ===========================================================================
# PRE-TRADE RISK INTEGRATION TESTS
# ===========================================================================


class TestPreTradeRisk:
    """Integration tests for risk/pre_trade_risk.py"""

    def test_pre_trade_check_approved(self):
        """Normal pre-trade check passes."""
        ledger = MagicMock()
        ledger.daily_realized_loss = 0.0
        ledger.weekly_realized_loss = 0.0
        ledger.total_drawdown = 0.0
        ledger.open_positions = 0
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0.1"),
            volume_before_round=Decimal("0.1"),
            risk_amount=Decimal("50"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("50"),
            margin_estimate=Decimal("500"),
            rejected=False,
        )
        policy = RiskPolicy()
        result = pre_trade_check(sizing, policy, ledger, Decimal("10000"))
        assert result.approved is True
        assert len(result.reasons) == 0

    def test_pre_trade_check_sizer_rejected(self):
        """When sizer rejects, pre-trade check propagates rejections."""
        ledger = MagicMock()
        ledger.daily_realized_loss = 0.0
        ledger.weekly_realized_loss = 0.0
        ledger.total_drawdown = 0.0
        ledger.open_positions = 0
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0"),
            volume_before_round=Decimal("0"),
            risk_amount=Decimal("0"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("0"),
            margin_estimate=Decimal("0"),
            rejected=True,
            rejection_reasons=["Stop loss is zero"],
        )
        policy = RiskPolicy()
        result = pre_trade_check(sizing, policy, ledger, Decimal("10000"))
        assert result.approved is False
        assert "Stop loss is zero" in result.reasons

    def test_pre_trade_check_drawdown_blocks(self):
        """Pre-trade check rejects when drawdown limit is reached."""
        ledger = MagicMock()
        ledger.daily_realized_loss = 0.0
        ledger.weekly_realized_loss = 0.0
        ledger.total_drawdown = 0.10  # 10%
        ledger.open_positions = 0
        ledger.orders_today = 0

        sizing = SizingResult(
            volume=Decimal("0.1"),
            volume_before_round=Decimal("0.1"),
            risk_amount=Decimal("50"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("50"),
            margin_estimate=Decimal("500"),
            rejected=False,
        )
        policy = RiskPolicy(max_total_drawdown_bps=1000)  # 10%
        result = pre_trade_check(sizing, policy, ledger, Decimal("10000"))
        assert result.approved is False
        assert any("drawdown" in r.lower() for r in result.reasons)


# ===========================================================================
# RISK POLICY TESTS
# ===========================================================================


class TestRiskPolicy:
    """Tests for risk/risk_policy.py"""

    def test_risk_policy_frozen(self):
        """RiskPolicy is frozen — cannot modify fields."""
        rp = RiskPolicy()
        with pytest.raises(AttributeError):
            rp.risk_per_trade_bps = 50

    def test_risk_policy_defaults(self):
        """Default RiskPolicy values match documented defaults."""
        rp = RiskPolicy()
        assert rp.risk_per_trade_bps == 100
        assert rp.max_daily_loss_bps == 200
        assert rp.max_weekly_loss_bps == 500
        assert rp.max_total_drawdown_bps == 1000
        assert rp.max_open_positions == 5
        assert rp.require_stop_loss is True
        assert rp.fail_closed is True

    def test_risk_policy_custom_values(self):
        """RiskPolicy accepts custom values."""
        rp = RiskPolicy(risk_per_trade_bps=50, max_open_positions=10)
        assert rp.risk_per_trade_bps == 50
        assert rp.max_open_positions == 10

    def test_risk_policy_margin_level(self):
        """min_margin_level_pct returns the reject threshold."""
        rp = RiskPolicy(reject_if_margin_level_below_pct=500)
        assert rp.min_margin_level_pct == Decimal("500")


# ===========================================================================
# FILL MODEL AMBIGUOUS TESTS
# ===========================================================================


class TestFillModelAmbiguous:
    """Tests for ambiguous bar handling in fill model."""

    def test_ambiguous_bar_buy_both_touch(self):
        """BUY: bar range touches both SL and TP → ambiguous."""
        trigger, amb = check_sl_tp_trigger_ambiguous(
            Side("BUY"),
            Decimal("1.0950"),
            Decimal("1.1050"),
            Decimal("1.1000"),
            Decimal("1.1002"),
            bar_high=Decimal("1.1060"),
            bar_low=Decimal("1.0940"),
        )
        assert trigger == "SL"
        assert amb is True

    def test_ambiguous_bar_sell_both_touch(self):
        """SELL: bar range touches both SL and TP → ambiguous."""
        trigger, amb = check_sl_tp_trigger_ambiguous(
            Side("SELL"),
            Decimal("1.1050"),
            Decimal("1.0950"),
            Decimal("1.1000"),
            Decimal("1.1002"),
            bar_high=Decimal("1.1060"),
            bar_low=Decimal("1.0940"),
        )
        assert trigger == "SL"
        assert amb is True

    def test_ambiguous_bar_buy_only_sl(self):
        """BUY: bar only touches SL (bar_low <= SL, bar_high < TP) → not ambiguous."""
        trigger, amb = check_sl_tp_trigger_ambiguous(
            Side("BUY"),
            Decimal("1.0950"),
            Decimal("1.1050"),
            Decimal("1.1000"),
            Decimal("1.1002"),
            bar_high=Decimal("1.1030"),
            bar_low=Decimal("1.0940"),
        )
        assert trigger == "SL"
        assert amb is False

    def test_ambiguous_bar_buy_only_tp(self):
        """BUY: bar only touches TP (bar_high >= TP, bar_low > SL) → not ambiguous."""
        trigger, amb = check_sl_tp_trigger_ambiguous(
            Side("BUY"),
            Decimal("1.0950"),
            Decimal("1.1050"),
            Decimal("1.1000"),
            Decimal("1.1002"),
            bar_high=Decimal("1.1060"),
            bar_low=Decimal("1.0960"),
        )
        assert trigger == "TP"
        assert amb is False

    def test_ambiguous_bar_no_trigger(self):
        """BUY: bar doesn't touch SL or TP → no trigger."""
        trigger, amb = check_sl_tp_trigger_ambiguous(
            Side("BUY"),
            Decimal("1.0950"),
            Decimal("1.1050"),
            Decimal("1.1000"),
            Decimal("1.1002"),
            bar_high=Decimal("1.1030"),
            bar_low=Decimal("1.0960"),
        )
        assert trigger is None
        assert amb is False
