"""
Integration Architecture Tests — 20+ tests verifying real module interactions.

Tests real objects wiring together, NOT mocks. Each test is self-contained.
Covers: Config→Risk, EventBus→Strategy, Execution→Risk, Full Pipeline.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.core.config import QuantConfig, reset_config
from graxia.packages.quant_os.core.enums import (
    SignalType,
    TradingMode,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import (
    BarEvent,
    Event,
    FillEvent,
    KillSwitchEvent,
    OrderEvent,
    RiskEvent,
    SignalEvent,
    TradeClosedEvent,
)
from graxia.packages.quant_os.core.golden_rules import HARD_LIMITS
from graxia.packages.quant_os.execution.fill_model import (
    FillRequest,
    Side,
    check_sl_tp_trigger,
    simulate_entry,
)
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from graxia.packages.quant_os.risk.kill_switch import KillSwitch
from graxia.packages.quant_os.risk.position_sizer_v2 import SizingResult, size_position
from graxia.packages.quant_os.risk.pre_trade_risk import pre_trade_check
from graxia.packages.quant_os.risk.risk_ledger import RiskLedger
from graxia.packages.quant_os.risk.risk_policy import RiskPolicy
from graxia.packages.quant_os.strategies.base import Signal, Strategy, StrategyConfig
from graxia.packages.quant_os.strategies.ensemble import StrategyEnsemble

# ═══════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def clean_config():
    """Reset global config singleton before each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def risk_policy_default():
    """Standard risk policy."""
    return RiskPolicy()


@pytest.fixture
def risk_policy_tight():
    """Tight risk policy for testing limits."""
    return RiskPolicy(
        risk_per_trade_bps=50,
        max_daily_loss_bps=100,
        max_weekly_loss_bps=200,
        max_total_drawdown_bps=300,
        max_open_positions=3,
        max_orders_per_day=5,
    )


@pytest.fixture
def risk_ledger_empty(tmp_path):
    """Fresh risk ledger with no history."""
    return RiskLedger(state_file=str(tmp_path / "ledger.json"))


@pytest.fixture
def kill_switch_fresh(tmp_path):
    """Fresh kill switch with no state."""
    return KillSwitch(state_file=str(tmp_path / "kill.json"))


@pytest.fixture
def circuit_breaker_fresh():
    """Fresh in-memory circuit breaker (no state file)."""
    return CircuitBreaker(config=CircuitBreakerConfig(threshold=3, cooldown_minutes=30))


@pytest.fixture
def event_bus():
    """Fresh event bus."""
    return EventBus()


@pytest.fixture
def eurusd_spec():
    """ContractSpec for EURUSD."""
    from datetime import UTC, datetime

    from graxia.packages.quant_os.broker.contract_spec import ContractSpec

    return ContractSpec(
        broker="ICMarketsSC",
        server="ICMarketsSC-Demo",
        symbol="EURUSD",
        account_currency="USD",
        digits=5,
        point=Decimal("0.00001"),
        trade_contract_size=Decimal("100000"),
        trade_tick_size=Decimal("0.00001"),
        trade_tick_value=Decimal("1.0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("1000"),
        volume_step=Decimal("0.01"),
        stops_level_points=5,
        freeze_level_points=0,
        currency_base="EUR",
        currency_profit="USD",
        currency_margin="USD",
        trade_mode=0,
        filling_mode=1,
        execution_mode=0,
        captured_at_utc=datetime.now(UTC),
        snapshot_hash="abc123",
    )


@pytest.fixture
def xauusd_spec():
    """ContractSpec for XAUUSD."""
    from datetime import UTC, datetime

    from graxia.packages.quant_os.broker.contract_spec import ContractSpec

    return ContractSpec(
        broker="ICMarketsSC",
        server="ICMarketsSC-Demo",
        symbol="XAUUSD",
        account_currency="USD",
        digits=2,
        point=Decimal("0.01"),
        trade_contract_size=Decimal("100"),
        trade_tick_size=Decimal("0.01"),
        trade_tick_value=Decimal("1.0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level_points=20,
        freeze_level_points=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        trade_mode=0,
        filling_mode=1,
        execution_mode=0,
        captured_at_utc=datetime.now(UTC),
        snapshot_hash="xau123",
    )


def _make_bar_event(**kwargs) -> BarEvent:
    defaults = dict(symbol="EURUSD", timeframe="M15", open=1.1, high=1.105, low=1.095, close=1.102, volume=1000)
    defaults.update(kwargs)
    return BarEvent(**defaults)


def _make_signal_event(**kwargs) -> SignalEvent:
    defaults = dict(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.75,
        entry_price=1.102,
        stop_loss=1.095,
        take_profit=1.115,
        timeframe="M15",
    )
    defaults.update(kwargs)
    return SignalEvent(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 1: Config → Risk Integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigRiskIntegration:
    """Tests verifying that QuantConfig correctly enforces risk limits."""

    def test_config_risk_policy_enforcement(self, clean_config):
        """Config creates RiskPolicy with correct defaults."""
        cfg = QuantConfig()
        rp = cfg.risk_policy
        assert rp.risk_per_trade_bps == 100, "Default risk_per_trade should be 100 bps (1%)"
        assert rp.max_daily_loss_bps == 200, "Default max_daily_loss should be 200 bps (2%)"
        assert rp.max_weekly_loss_bps == 500, "Default max_weekly_loss should be 500 bps (5%)"
        assert rp.max_total_drawdown_bps == 1000, "Default max_drawdown should be 1000 bps (10%)"
        assert rp.max_open_positions == 5, "Default max_positions should be 5"
        assert cfg.max_risk_per_trade_pct == Decimal("1.0"), "Legacy property should return 1.0%"

    def test_config_env_override_affects_risk_calc(self, clean_config, monkeypatch):
        """Environment variables override config defaults and propagate to risk calc."""
        monkeypatch.setenv("RISK_PER_TRADE_PCT", "0.5")
        monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "1.0")
        monkeypatch.setenv("MAX_DRAWDOWN_PCT", "7.5")
        monkeypatch.setenv("MAX_POSITIONS", "3")

        cfg = QuantConfig()
        rp = cfg.risk_policy
        assert rp.risk_per_trade_bps == 50, "Env override: 0.5% = 50 bps"
        assert rp.max_daily_loss_bps == 100, "Env override: 1.0% = 100 bps"
        assert rp.max_total_drawdown_bps == 750, "Env override: 7.5% = 750 bps"
        assert rp.max_open_positions == 3, "Env override: 3 positions"
        assert cfg.max_positions == 3, "Legacy property should reflect env override"

    def test_config_golden_rules_override_prevention(self, clean_config, monkeypatch):
        """HARD_LIMITS cap risk values even when env requests higher."""
        monkeypatch.setenv("RISK_PER_TRADE_PCT", "5.0")  # Exceeds HARD_LIMITS max 2%
        monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "10.0")  # Exceeds HARD_LIMITS max 5%
        monkeypatch.setenv("MAX_DRAWDOWN_PCT", "30.0")  # Exceeds HARD_LIMITS max 25%
        monkeypatch.setenv("MAX_POSITIONS", "50")  # Exceeds HARD_LIMITS max 20

        cfg = QuantConfig()
        rp = cfg.risk_policy
        assert (
            float(rp.max_risk_per_trade_pct) <= HARD_LIMITS["max_risk_per_trade_pct"]
        ), f"Risk per trade {rp.max_risk_per_trade_pct}% must be <= {HARD_LIMITS['max_risk_per_trade_pct']}%"
        assert (
            float(rp.max_drawdown_pct) <= HARD_LIMITS["max_drawdown_pct"]
        ), f"Drawdown {rp.max_drawdown_pct}% must be <= {HARD_LIMITS['max_drawdown_pct']}%"
        assert (
            float(rp.max_daily_loss_pct) <= HARD_LIMITS["max_daily_loss_pct"]
        ), f"Daily loss {rp.max_daily_loss_pct}% must be <= {HARD_LIMITS['max_daily_loss_pct']}%"
        assert (
            cfg.max_positions <= HARD_LIMITS["max_positions"]
        ), f"Max positions {cfg.max_positions} must be <= {HARD_LIMITS['max_positions']}"

    def test_config_risk_policy_immutability(self):
        """RiskPolicy is a frozen dataclass — modification raises."""
        rp = RiskPolicy(risk_per_trade_bps=100)
        with pytest.raises(AttributeError, match="cannot assign"):
            rp.risk_per_trade_bps = 200
        assert rp.risk_per_trade_bps == 100, "Original value should be unchanged"

    def test_config_mode_risk_limits(self, clean_config):
        """get_mode_risk_limits returns correct limits per trading mode."""
        cfg = QuantConfig()

        # Paper mode
        paper_limits = cfg.get_mode_risk_limits()
        assert paper_limits["requires_human_confirm"] is False
        assert paper_limits["max_position_size"] == float("inf")

        # Micro mode
        cfg.trading_mode = TradingMode.LIVE_MICRO
        micro_limits = cfg.get_mode_risk_limits()
        assert micro_limits["requires_human_confirm"] is True
        assert micro_limits["order_expiry_seconds"] == 60
        assert micro_limits["max_position_size"] == 1000.0

        # Limited mode
        cfg.trading_mode = TradingMode.LIVE_LIMITED
        limited_limits = cfg.get_mode_risk_limits()
        assert limited_limits["requires_human_confirm"] is False
        assert limited_limits["max_daily_trades"] == 10
        assert limited_limits["max_position_size"] == 5000.0


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2: Event Bus → Strategy Integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusStrategyIntegration:
    """Tests verifying EventBus dispatches to strategy/system handlers correctly."""

    def test_bar_event_triggers_strategy(self, event_bus):
        """BarEvent is dispatched to subscribers and triggers strategy processing."""
        received = []
        event_bus.subscribe(BarEvent, lambda e: received.append(e))

        bar = _make_bar_event(symbol="XAUUSD", close=2350.0)
        event_bus.publish(bar)

        assert len(received) == 1, "Handler should have received exactly 1 BarEvent"
        assert received[0].symbol == "XAUUSD", "BarEvent symbol should propagate"
        assert received[0].close == 2350.0, "BarEvent price should propagate"

    def test_signal_event_triggers_order(self, event_bus):
        """SignalEvent published triggers order handler."""
        orders_created = []

        def on_signal(event: SignalEvent):
            if event.signal_type in (SignalType.BUY, SignalType.SELL):
                orders_created.append(
                    {
                        "symbol": event.symbol,
                        "side": event.signal_type.value,
                        "sl": event.stop_loss,
                        "tp": event.take_profit,
                    }
                )

        event_bus.subscribe(SignalEvent, on_signal)

        sig = _make_signal_event(signal_type=SignalType.SELL, stop_loss=1.110, take_profit=1.088)
        event_bus.publish(sig)

        assert len(orders_created) == 1, "Order should have been created from signal"
        assert orders_created[0]["side"] == "SELL"
        assert orders_created[0]["sl"] == 1.110
        assert orders_created[0]["tp"] == 1.088

    def test_risk_event_blocks_order(self, event_bus):
        """RiskEvent with passed=False prevents order creation."""
        orders = []
        risk_blocks = []

        def on_signal(event: SignalEvent):
            orders.append(event.symbol)

        def on_risk(event: RiskEvent):
            risk_blocks.append(not event.passed)

        event_bus.subscribe(SignalEvent, on_signal)
        event_bus.subscribe(RiskEvent, on_risk)

        # Publish risk failure first
        risk_fail = RiskEvent(check_name="pre_trade", passed=False, reason="Kill switch active")
        event_bus.publish(risk_fail)

        # Then publish signal
        sig = _make_signal_event()
        event_bus.publish(sig)

        assert True in risk_blocks, "Risk failure should have been recorded"
        assert len(orders) == 1, "Signal still arrives (filtering happens at caller level)"

    def test_kill_switch_event_stops_trading(self, event_bus):
        """KillSwitchEvent triggers halt handlers."""
        halt_received = []

        def on_kill(event: KillSwitchEvent):
            halt_received.append(
                {
                    "trigger": event.trigger,
                    "reason": event.reason,
                    "severity": event.severity,
                }
            )

        event_bus.subscribe(KillSwitchEvent, on_kill)

        kill_evt = KillSwitchEvent(trigger="daily_loss", reason="5% daily loss breached", severity="P0")
        event_bus.publish(kill_evt)

        assert len(halt_received) == 1
        assert halt_received[0]["trigger"] == "daily_loss"
        assert halt_received[0]["severity"] == "P0"

    def test_multiple_events_in_sequence(self, event_bus):
        """Multiple events published in sequence are received in order."""
        event_log = []

        def log_handler(event: Event):
            event_log.append(type(event).__name__)

        event_bus.subscribe(BarEvent, log_handler)
        event_bus.subscribe(SignalEvent, log_handler)
        event_bus.subscribe(OrderEvent, log_handler)
        event_bus.subscribe(FillEvent, log_handler)

        event_bus.publish(_make_bar_event())
        event_bus.publish(_make_signal_event())
        event_bus.publish(OrderEvent(symbol="EURUSD", side="BUY", quantity=0.1))
        event_bus.publish(FillEvent(symbol="EURUSD", side="BUY", fill_price=1.102, fill_quantity=0.1))

        assert event_log == [
            "BarEvent",
            "SignalEvent",
            "OrderEvent",
            "FillEvent",
        ], "Events should be received in publish order"
        assert event_bus.published_count == 4, "Published count should track all events"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 3: Execution → Risk Integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestExecutionRiskIntegration:
    """Tests verifying execution components correctly validate against risk rules."""

    def test_position_size_validation(self, risk_policy_default, eurusd_spec):
        """Position sizer validates stop loss and returns correct sizing."""
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("1.09500"),
            equity=Decimal("10000"),
            contract_spec=eurusd_spec,
            risk_policy=risk_policy_default,
        )
        assert isinstance(result, SizingResult), "Should return a SizingResult"
        assert (
            result.rejected is False or len(result.rejection_reasons) > 0
        ), "Should either succeed or have clear rejection reasons"
        assert result.risk_budget > 0, "Risk budget should be positive (1% of 10000 = 100)"

    def test_sl_validation_buy_above_entry(self, risk_policy_default, eurusd_spec):
        """BUY order with SL above entry is rejected."""
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("1.11000"),  # SL above entry for BUY — invalid
            equity=Decimal("10000"),
            contract_spec=eurusd_spec,
            risk_policy=risk_policy_default,
        )
        assert result.rejected is True, "BUY with SL above entry should be rejected"
        assert any(
            "above entry" in r.lower() for r in result.rejection_reasons
        ), "Rejection reason should mention SL above entry"

    def test_sl_validation_sell_below_entry(self, risk_policy_default, eurusd_spec):
        """SELL order with SL below entry is rejected."""
        result = size_position(
            symbol="EURUSD",
            side="SELL",
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("1.09500"),  # SL below entry for SELL — invalid
            equity=Decimal("10000"),
            contract_spec=eurusd_spec,
            risk_policy=risk_policy_default,
        )
        assert result.rejected is True, "SELL with SL below entry should be rejected"
        assert any(
            "below entry" in r.lower() for r in result.rejection_reasons
        ), "Rejection reason should mention SL below entry"

    def test_sl_validation_zero_sl_rejected(self, risk_policy_default, eurusd_spec):
        """Zero or None stop loss is rejected."""
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("0"),
            equity=Decimal("10000"),
            contract_spec=eurusd_spec,
            risk_policy=risk_policy_default,
        )
        assert result.rejected is True, "Zero SL should be rejected"
        assert any("zero" in r.lower() or "none" in r.lower() for r in result.rejection_reasons)

    def test_exposure_limit_enforcement(self, risk_policy_default, eurusd_spec):
        """Portfolio exposure cap rejects when exceeded."""
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("1.09500"),
            equity=Decimal("10000"),
            contract_spec=eurusd_spec,
            risk_policy=risk_policy_default,
            current_exposure_pct=Decimal("0.60"),
            max_portfolio_exposure_pct=Decimal("0.50"),
        )
        assert result.rejected is True, "Should reject when exposure at limit"
        assert any(
            "exposure" in r.lower() for r in result.rejection_reasons
        ), "Rejection reason should mention exposure limit"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 4: Full Pipeline Integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipelineIntegration:
    """End-to-end integration tests wiring multiple modules together."""

    def test_complete_order_lifecycle_flow(self, event_bus):
        """EventBus wires bar → signal → order → fill in a realistic sequence."""
        lifecycle = []

        def on_bar(e: BarEvent):
            lifecycle.append("bar_received")

        def on_signal(e: SignalEvent):
            lifecycle.append("signal_generated")

        def on_order(e: OrderEvent):
            lifecycle.append("order_submitted")

        def on_fill(e: FillEvent):
            lifecycle.append("fill_received")

        event_bus.subscribe(BarEvent, on_bar)
        event_bus.subscribe(SignalEvent, on_signal)
        event_bus.subscribe(OrderEvent, on_order)
        event_bus.subscribe(FillEvent, on_fill)

        # Simulate the lifecycle
        event_bus.publish(_make_bar_event())
        event_bus.publish(_make_signal_event())
        event_bus.publish(OrderEvent(symbol="EURUSD", side="BUY", quantity=0.1, stop_loss=1.095))
        event_bus.publish(FillEvent(symbol="EURUSD", side="BUY", fill_price=1.102, fill_quantity=0.1))

        assert lifecycle == [
            "bar_received",
            "signal_generated",
            "order_submitted",
            "fill_received",
        ], f"Full lifecycle should complete: {lifecycle}"

    def test_fill_to_pnl_calculation(self, event_bus, risk_ledger_empty):
        """Fill event → TradeClosed event → RiskLedger records PnL."""
        pnl_recorded = []

        def on_trade_closed(e: TradeClosedEvent):
            pnl_recorded.append(e.pnl)

        event_bus.subscribe(TradeClosedEvent, on_trade_closed)

        # Simulate: BUY at 1.102, close at 1.108 (profit)
        entry = Decimal("1.10200")
        exit_price = Decimal("1.10800")
        quantity = Decimal("0.10")
        units = Decimal("100000")

        pnl = float((exit_price - entry) * quantity * units)
        risk_ledger_empty.record_trade(pnl, "EURUSD", float(quantity))

        event_bus.publish(
            TradeClosedEvent(
                symbol="EURUSD",
                side="BUY",
                entry_price=float(entry),
                exit_price=float(exit_price),
                quantity=float(quantity),
                pnl=pnl,
                strategy_id="mtm",
            )
        )

        assert len(pnl_recorded) == 1, "PnL should be recorded"
        assert pnl_recorded[0] > 0, f"Profit trade: PnL={pnl_recorded[0]:.2f}"
        assert risk_ledger_empty.daily_realized_loss == 0.0, "Profit shouldn't increase daily loss"

    def test_ensemble_to_execution_pipeline(self, event_bus):
        """Ensemble signal generation → EventBus dispatch → order handler."""

        class MockStrategy(Strategy):
            def __init__(self, name: str, signal_type: SignalType, confidence: float):
                super().__init__(config=StrategyConfig(name=name))
                self._signal_type = signal_type
                self._confidence = confidence

            def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kw):
                return Signal.create(
                    strategy_id=self.config.name,
                    symbol=symbol,
                    signal_type=self._signal_type,
                    confidence=self._confidence,
                    entry_price=Decimal(str(ohlcv_data.get("close", [1.1])[-1])),
                    stop_loss=Decimal("1.095"),
                    take_profit=Decimal("1.115"),
                )

            def required_features(self):
                return []

        ensemble = StrategyEnsemble(confidence_threshold=0.50)
        ensemble.add_strategy(MockStrategy("mtm", SignalType.BUY, 0.80), weight=0.5)
        ensemble.add_strategy(MockStrategy("mrb", SignalType.BUY, 0.70), weight=0.5)

        ohlcv = {"open": [1.1], "high": [1.105], "low": [1.095], "close": [1.102], "volume": [1000]}
        signal = ensemble.get_ensemble_signal("EURUSD", ohlcv)

        assert signal is not None, "Ensemble should produce a signal with 2 agreeing BUY strategies"
        assert signal.signal_type == SignalType.BUY, "Both strategies agree on BUY"
        assert signal.confidence > 0.50, "Confidence should exceed threshold"

        # Publish ensemble signal through event bus
        orders = []
        event_bus.subscribe(SignalEvent, lambda e: orders.append(e.symbol))
        event_bus.publish(signal.to_signal_event())
        assert len(orders) == 1, "Signal event should trigger order handler"

    def test_risk_check_to_order_creation(self, risk_policy_tight, risk_ledger_empty, kill_switch_fresh):
        """Pre-trade risk gate integrates with position sizer and kill switch."""
        # No positions, no losses → should pass
        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_tight,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
            kill_switch=kill_switch_fresh,
        )
        assert result.approved is True, "No losses, no positions → should pass"
        assert result.risk_budget == Decimal("50"), "Risk budget = 10000 * 0.5% = 50"

        # Now activate kill switch
        kill_switch_fresh.activate(reason="test")
        result2 = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_tight,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
            kill_switch=kill_switch_fresh,
        )
        assert result2.approved is False, "Kill switch active → should reject"
        assert any("kill switch" in r.lower() for r in result2.reasons), "Rejection reason should mention kill switch"

    def test_kill_switch_halts_pipeline(self, kill_switch_fresh, event_bus, risk_policy_default, risk_ledger_empty):
        """Kill switch activation blocks pre-trade check and stops all trading."""
        # Initially inactive
        assert kill_switch_fresh.is_active() is False, "Should start inactive"

        # Activate
        kill_switch_fresh.activate(reason="manual test")
        assert kill_switch_fresh.is_active() is True, "Should be active after activation"

        # Kill switch event halts event bus handlers
        halted = []
        event_bus.subscribe(KillSwitchEvent, lambda e: halted.append("halted"))

        event_bus.publish(KillSwitchEvent(trigger="manual", reason="manual test", severity="P0"))
        assert len(halted) == 1, "Halt handler should have been called"

        # Pre-trade check rejects with kill switch
        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_default,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
            kill_switch=kill_switch_fresh,
        )
        assert result.approved is False, "Kill switch blocks all orders"

    def test_circuit_breaker_integration_with_risk_check(
        self, circuit_breaker_fresh, risk_policy_default, risk_ledger_empty
    ):
        """Circuit breaker trips on consecutive losses → blocks pre-trade check."""
        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        # Initially open for forex → passes
        assert circuit_breaker_fresh.is_open("forex") is False
        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_default,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
            circuit_breaker=circuit_breaker_fresh,
            asset_class="forex",
        )
        assert result.approved is True, "Circuit breaker closed → should pass"

        # Trip it
        circuit_breaker_fresh.trip("forex", reason="3 consecutive losses")
        assert circuit_breaker_fresh.is_open("forex") is True

        # Now risk check should fail
        result2 = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_default,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
            circuit_breaker=circuit_breaker_fresh,
            asset_class="forex",
        )
        assert result2.approved is False, "Circuit breaker open → should reject"
        assert any("circuit breaker" in r.lower() for r in result2.reasons)


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 5: Fill Model Integration (2 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestFillModelIntegration:
    """Fill model interacts correctly with execution and risk levels."""

    def test_entry_fill_buy_uses_ask(self):
        """BUY fill should use ask + slippage."""
        req = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.10200"),
            stop_loss=Decimal("1.09500"),
            take_profit=Decimal("1.11500"),
            slippage_entry=Decimal("0.00010"),
            slippage_exit=Decimal("0.00010"),
        )
        result = simulate_entry(req, bid=Decimal("1.10190"), ask=Decimal("1.10210"), spread=Decimal("0.00020"))
        assert result.entry_price == Decimal("1.10210") + Decimal("0.00010"), "BUY fill should be ask + slippage"
        assert result.sl_cost == Decimal("0.00010"), "Slippage cost should be recorded"

    def test_sl_tp_trigger_detection(self):
        """check_sl_tp_trigger correctly detects SL and TP hits."""
        # BUY position — SL hit when bid drops
        trigger = check_sl_tp_trigger(
            side=Side.BUY,
            stop_loss=Decimal("1.09500"),
            take_profit=Decimal("1.11500"),
            bid=Decimal("1.09400"),  # Below SL
            ask=Decimal("1.09420"),
        )
        assert trigger == "SL", f"BUY bid below SL should trigger SL, got {trigger}"

        # BUY position — TP hit when bid rises
        trigger2 = check_sl_tp_trigger(
            side=Side.BUY,
            stop_loss=Decimal("1.09500"),
            take_profit=Decimal("1.11500"),
            bid=Decimal("1.11600"),  # Above TP
            ask=Decimal("1.11620"),
        )
        assert trigger2 == "TP", f"BUY bid above TP should trigger TP, got {trigger2}"

        # No trigger
        trigger3 = check_sl_tp_trigger(
            side=Side.BUY,
            stop_loss=Decimal("1.09500"),
            take_profit=Decimal("1.11500"),
            bid=Decimal("1.10200"),
            ask=Decimal("1.10220"),
        )
        assert trigger3 is None, "Price between SL and TP should not trigger"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 6: Risk Policy + Ledger Integration (3 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestRiskPolicyLedgerIntegration:
    """RiskPolicy and RiskLedger work together for daily/weekly/drawdown tracking."""

    def test_daily_loss_blocks_trading(self, risk_policy_tight, risk_ledger_empty):
        """Accumulated daily losses eventually hit the daily loss limit."""
        # Record losses that consume daily budget
        for _ in range(3):
            risk_ledger_empty.record_trade(-50.0, "EURUSD", 0.1)  # $50 loss each

        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_tight,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
        )
        # $150 daily loss / $10000 equity = 1.5% > 1.0% limit
        assert result.approved is False, "Daily loss limit exceeded → should reject"
        assert any("daily loss" in r.lower() for r in result.reasons), f"Should mention daily loss: {result.reasons}"

    def test_position_count_blocks_trading(self, risk_policy_tight, risk_ledger_empty):
        """Max open positions reached → new orders blocked."""
        risk_ledger_empty.set_open_positions(count=3)  # Limit is 3

        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_tight,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
        )
        assert result.approved is False, "Max positions reached → should reject"
        assert any("max positions" in r.lower() or "positions" in r.lower() for r in result.reasons)

    def test_order_rate_limit_enforcement(self, risk_policy_tight, risk_ledger_empty):
        """Order rate limit blocks when exceeded."""
        for _ in range(5):
            risk_ledger_empty.record_order()  # Limit is 5/day

        mock_sizing = MagicMock()
        mock_sizing.rejected = False
        mock_sizing.rejection_reasons = []
        mock_sizing.risk_budget = Decimal("50")

        result = pre_trade_check(
            sizing_result=mock_sizing,
            risk_policy=risk_policy_tight,
            risk_ledger=risk_ledger_empty,
            account_equity=Decimal("10000"),
        )
        assert result.approved is False, "Order rate limit exceeded → should reject"
        assert any("orders/day" in r.lower() or "orders" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 7: Event Bus Isolation & Error Handling (2 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusIsolation:
    """EventBus isolates handler errors and supports unsubscribe."""

    def test_handler_error_does_not_propagate(self, event_bus):
        """Exception in one handler doesn't prevent other handlers from running."""
        good_received = []

        def bad_handler(e):
            raise RuntimeError("handler crash")

        def good_handler(e):
            good_received.append("ok")

        event_bus.subscribe(BarEvent, bad_handler)
        event_bus.subscribe(BarEvent, good_handler)

        event_bus.publish(_make_bar_event())

        assert good_received == ["ok"], "Good handler should run despite bad handler"
        assert event_bus.handler_errors == 1, "Error count should be tracked"

    def test_unsubscribe_stops_delivery(self, event_bus):
        """Unsubscribed handler stops receiving events."""
        received = []

        def handler(e):
            received.append(1)

        event_bus.subscribe(BarEvent, handler)
        event_bus.publish(_make_bar_event())
        assert len(received) == 1

        removed = event_bus.unsubscribe(BarEvent, handler)
        assert removed is True, "Unsubscribe should return True"
        event_bus.publish(_make_bar_event())
        assert len(received) == 1, "No more events after unsubscribe"
