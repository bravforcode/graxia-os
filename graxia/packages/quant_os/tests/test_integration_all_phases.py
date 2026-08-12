"""D1: Comprehensive integration tests for Phase A features.

Validates that strategies, events, event bus, and Kelly sizing work together.
≥20 test cases covering happy path + edge cases.
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.enums import (
    CloseReason,
    OrderSide,
    RegimeType,
    SignalType,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import (
    BarEvent,
    Event,
    FillEvent,
    KillSwitchEvent,
    OrderEvent,
    RegimeChangeEvent,
    SignalEvent,
    TradeClosedEvent,
)
from graxia.packages.quant_os.risk.position_sizer import (
    AntiMartingaleSizer,
    ATRSizer,
    FixedFractionalSizer,
    KellySizer,
    TradeStatsTracker,
    kelly_fraction,
)
from graxia.packages.quant_os.strategies.base import (
    HyperparameterRange,
    Signal,
    Strategy,
    StrategyConfig,
)

# ── Test Strategies ──────────────────────────────────────────────


class MomentumStrategy(Strategy):
    """Concrete strategy that reads bar data and emits signals via should_long."""

    def __init__(self):
        super().__init__(StrategyConfig(name="Momentum", symbols=["XAUUSD"]))
        self._last_bar_close = None

    def should_long(self, data):
        close = data.get("close", 0)
        ema = data.get("ema_20", 0)
        return close > ema

    def should_short(self, data):
        close = data.get("close", 0)
        ema = data.get("ema_20", 0)
        return close < ema

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        closes = ohlcv_data.get("close", [])
        if not closes:
            return None
        last_close = closes[-1]
        ema20 = (indicators or {}).get("ema_20", last_close)
        data = {"close": last_close, "ema_20": ema20}
        if self.should_long(data):
            self.signals_generated += 1
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.75,
            )
        if self.should_short(data):
            self.signals_generated += 1
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.70,
            )
        return None

    def required_features(self):
        return ["ema_20"]


class AdaptiveLossStrategy(Strategy):
    """Strategy that tracks consecutive losses via on_trade_closed."""

    def __init__(self):
        super().__init__()
        self.consecutive_losses = 0
        self.max_consecutive_losses_seen = 0

    def on_trade_closed(self, trade):
        if trade.pnl < 0:
            self.consecutive_losses += 1
            self.max_consecutive_losses_seen = max(self.max_consecutive_losses_seen, self.consecutive_losses)
        else:
            self.consecutive_losses = 0

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class OptunaReadyStrategy(Strategy):
    """Strategy with hyperparameters for Optuna tuning."""

    def __init__(self):
        super().__init__()
        self.ema_fast = 9
        self.ema_slow = 21
        self.atr_mult = 1.5

    def hyperparameters(self):
        return {
            "ema_fast": HyperparameterRange("ema_fast", 5, 20, step=1),
            "ema_slow": HyperparameterRange("ema_slow", 15, 50, step=1),
            "atr_mult": HyperparameterRange("atr_mult", 1.0, 3.0, step=0.1),
        }

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return [f"ema_{self.ema_fast}", f"ema_{self.ema_slow}", "atr"]


class RegimeFilteredStrategy(Strategy):
    """Strategy only valid in trending regimes."""

    def __init__(self):
        super().__init__(
            StrategyConfig(
                name="RegimeFilter",
                regime_filter=[RegimeType.TREND_STRONG_UP, RegimeType.TREND_STRONG_DOWN],
            )
        )

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        if regime and self.is_valid_for_regime(regime):
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.9,
            )
        return None

    def required_features(self):
        return []


class RiskAwareStrategy(Strategy):
    """Strategy that uses balance and position properties for sizing."""

    def __init__(self):
        super().__init__()

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        if self.balance is None or self.price is None:
            return None
        entry = self.price
        sl = entry * Decimal("0.99")  # 1% stop
        # Use a small units_per_lot so sizing works with test balances
        size = self.calculate_position_size(
            account_balance=self.balance,
            entry_price=entry,
            stop_loss=sl,
            units_per_lot=1.0,
        )
        if size > 0:
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=float(entry),
                stop_loss=float(sl),
            )
        return None

    def required_features(self):
        return []


# ── 1. Strategy + Event Bus integration ──────────────────────────


class TestStrategyEventBusIntegration:
    def test_strategy_receives_bar_and_emits_signal_via_bus(self):
        bus = EventBus()
        strategy = MomentumStrategy()
        emitted_signals: list[SignalEvent] = []

        def on_bar(bar: BarEvent):
            ohlcv = {"close": [bar.close]}
            indicators = {"ema_20": 3300.0}
            signal = strategy.generate_signal(bar.symbol, ohlcv, indicators)
            if signal:
                emitted_signals.append(
                    SignalEvent(
                        symbol=signal.symbol,
                        signal_type=signal.signal_type.value,
                        confidence=signal.confidence,
                    )
                )

        bus.subscribe(BarEvent, on_bar)
        bus.publish(BarEvent(symbol="XAUUSD", close=3350.0))
        bus.publish(BarEvent(symbol="XAUUSD", close=3250.0))

        assert len(emitted_signals) == 2
        assert emitted_signals[0].signal_type == "BUY"
        assert emitted_signals[1].signal_type == "SELL"
        assert strategy.signals_generated == 2

    def test_no_signal_when_neither_long_nor_short(self):
        bus = EventBus()
        strategy = MomentumStrategy()
        emitted = []

        def on_bar(bar: BarEvent):
            ohlcv = {"close": [bar.close]}
            indicators = {"ema_20": bar.close}  # flat — no crossover
            sig = strategy.generate_signal(bar.symbol, ohlcv, indicators)
            if sig:
                emitted.append(sig)

        bus.subscribe(BarEvent, on_bar)
        bus.publish(BarEvent(symbol="XAUUSD", close=3300.0))
        assert len(emitted) == 0
        assert strategy.signals_generated == 0


# ── 2. Full pipeline: Bar → Strategy → Signal → Order ───────────


class TestFullPipelineIntegration:
    def test_bar_to_order_pipeline(self):
        bus = EventBus()
        strategy = MomentumStrategy()
        orders: list[OrderEvent] = []

        def on_bar(bar: BarEvent):
            ohlcv = {"close": [bar.close]}
            indicators = {"ema_20": 3300.0}
            sig = strategy.generate_signal(bar.symbol, ohlcv, indicators)
            if sig:
                bus.publish(
                    SignalEvent(
                        symbol=sig.symbol,
                        signal_type=sig.signal_type.value,
                        confidence=sig.confidence,
                    )
                )

        def on_signal(sig: SignalEvent):
            if sig.signal_type == "BUY" and sig.confidence >= 0.6:
                orders.append(
                    OrderEvent(
                        symbol=sig.symbol,
                        side="BUY",
                        quantity=0.01,
                        strategy_id=strategy.id,
                    )
                )

        bus.subscribe(BarEvent, on_bar)
        bus.subscribe(SignalEvent, on_signal)

        bus.publish(BarEvent(symbol="XAUUSD", close=3350.0))
        assert len(orders) == 1
        assert orders[0].side == "BUY"
        assert orders[0].symbol == "XAUUSD"

    def test_bar_to_fill_to_trade_closed_lifecycle(self):
        bus = EventBus()
        fills: list[FillEvent] = []
        trades_closed: list[TradeClosedEvent] = []

        bus.subscribe(FillEvent, lambda e: fills.append(e))
        bus.subscribe(TradeClosedEvent, lambda e: trades_closed.append(e))

        bus.publish(
            FillEvent(
                order_id="ord_1",
                symbol="XAUUSD",
                side="BUY",
                fill_price=3300.0,
                fill_quantity=0.01,
            )
        )
        bus.publish(
            TradeClosedEvent(
                trade_id="trd_1",
                symbol="XAUUSD",
                side="BUY",
                entry_price=3300.0,
                exit_price=3340.0,
                quantity=0.01,
                pnl=0.40,
                close_reason="TAKE_PROFIT",
            )
        )

        assert len(fills) == 1
        assert len(trades_closed) == 1
        assert trades_closed[0].pnl == 0.40


# ── 3. Kelly sizing + TradeStatsTracker integration ──────────────


class TestKellySizingIntegration:
    def test_kelly_fraction_basic(self):
        f = kelly_fraction(win_rate=0.55, avg_win=1.5, avg_loss=1.0, fraction=0.25)
        assert 0.0 < f < 0.25

    def test_kelly_fraction_no_edge(self):
        f = kelly_fraction(win_rate=0.3, avg_win=1.0, avg_loss=1.5, fraction=0.25)
        assert f == 0.0

    def test_kelly_fraction_edge_cases(self):
        assert kelly_fraction(win_rate=0.0, avg_win=1.0, avg_loss=1.0) == 0.0
        assert kelly_fraction(win_rate=1.0, avg_win=1.0, avg_loss=1.0) == 0.0
        assert kelly_fraction(win_rate=0.5, avg_win=1.0, avg_loss=0.0) == 0.0

    def test_tracker_feeds_kelly(self):
        tracker = TradeStatsTracker(window=50)
        pnls = [100, -50, 80, -30, 120, -40, 90, -20, 110, -60]
        for p in pnls:
            tracker.record(p)

        assert tracker.trade_count == 10
        assert 0.0 < tracker.win_rate < 1.0
        assert tracker.avg_win > 0
        assert tracker.avg_loss > 0

        f = kelly_fraction(
            win_rate=tracker.win_rate,
            avg_win=tracker.avg_win,
            avg_loss=tracker.avg_loss,
            fraction=0.25,
        )
        assert f >= 0.0

    def test_tracker_sliding_window(self):
        tracker = TradeStatsTracker(window=5)
        for _ in range(10):
            tracker.record(100.0)
        for _ in range(5):
            tracker.record(-50.0)
        assert tracker.trade_count == 5  # window=5

    def test_tracker_profit_factor(self):
        tracker = TradeStatsTracker(window=100)
        tracker.record(100)
        tracker.record(100)
        tracker.record(-50)
        pf = tracker.profit_factor
        assert pf == pytest.approx(200 / 50, rel=1e-9)


# ── 4. Event round-trip serialization ────────────────────────────


class TestEventSerialization:
    @pytest.mark.parametrize(
        "event_cls,kwargs",
        [
            (BarEvent, {"symbol": "XAUUSD", "close": 3340.0}),
            (SignalEvent, {"symbol": "EURUSD", "confidence": 0.85}),
            (OrderEvent, {"symbol": "GBPUSD", "side": "BUY", "quantity": 0.1}),
            (FillEvent, {"symbol": "USDJPY", "fill_price": 150.5}),
            (TradeClosedEvent, {"symbol": "XAUUSD", "pnl": 1.23}),
            (KillSwitchEvent, {"trigger": "DAILY_LOSS", "reason": "exceeded"}),
            (RegimeChangeEvent, {"symbol": "XAUUSD", "new_regime": "CRISIS"}),
        ],
    )
    def test_event_to_dict_round_trip(self, event_cls, kwargs):
        event = event_cls(**kwargs)
        d = event.to_dict()
        assert d["event_type"] == event_cls.__name__
        assert "event_id" in d
        assert "timestamp" in d
        serialized = json.dumps(d, default=str)
        assert len(serialized) > 0

    def test_bar_event_to_dict_completeness(self):
        bar = BarEvent(symbol="XAUUSD", open=3300, high=3350, low=3290, close=3340, volume=500)
        d = bar.to_dict()
        assert d["open"] == 3300
        assert d["high"] == 3350
        assert d["low"] == 3290
        assert d["close"] == 3340
        assert d["volume"] == 500

    def test_event_frozen_immutability(self):
        bar = BarEvent(symbol="XAUUSD")
        with pytest.raises(AttributeError):
            bar.symbol = "EURUSD"


# ── 5. EventBus handler isolation ────────────────────────────────


class TestEventBusIsolation:
    def test_bad_handler_does_not_block_good(self):
        bus = EventBus()
        good = []

        def crash_handler(e):
            raise RuntimeError("oops")

        def good_handler(e):
            good.append(e)

        bus.subscribe(BarEvent, crash_handler)
        bus.subscribe(BarEvent, good_handler)
        bus.publish(BarEvent())
        assert len(good) == 1
        assert bus.handler_errors == 1

    def test_multiple_errors_counted(self):
        bus = EventBus()

        def always_fail(e):
            raise ValueError("fail")

        bus.subscribe(BarEvent, always_fail)
        bus.publish(BarEvent())
        bus.publish(BarEvent())
        assert bus.handler_errors == 2

    def test_unsubscribe_nonexistent_returns_false(self):
        bus = EventBus()
        assert bus.unsubscribe(BarEvent, lambda e: None) is False

    def test_clear_removes_all_handlers(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(SignalEvent, lambda e: None)
        bus.clear()
        assert bus.subscriber_count() == 0

    def test_base_event_handler_receives_all(self):
        bus = EventBus()
        all_events = []
        bus.subscribe(Event, lambda e: all_events.append(type(e).__name__))
        bus.publish(BarEvent())
        bus.publish(SignalEvent())
        bus.publish(KillSwitchEvent())
        assert all_events == ["BarEvent", "SignalEvent", "KillSwitchEvent"]

    def test_publish_count_tracks_all(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.publish(BarEvent())
        bus.publish(SignalEvent())
        bus.publish(BarEvent())
        assert bus.published_count == 3

    def test_subscriber_count_per_type(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(BarEvent, lambda e: None)
        bus.subscribe(OrderEvent, lambda e: None)
        assert bus.subscriber_count(BarEvent) == 2
        assert bus.subscriber_count(OrderEvent) == 1
        assert bus.subscriber_count() == 3


# ── 6. Strategy helper methods with runtime state ────────────────


class TestStrategyRuntimeState:
    def test_set_runtime_state_injects_price_balance(self):
        s = MomentumStrategy()
        s.set_runtime_state(
            price=Decimal("3340.50"),
            balance=Decimal("10000"),
            available_margin=Decimal("9500"),
        )
        assert s.price == Decimal("3340.50")
        assert s.balance == Decimal("10000")
        assert s.available_margin == Decimal("9500")

    def test_position_property(self):
        s = MomentumStrategy()
        pos = {"symbol": "XAUUSD", "side": "BUY", "qty": 0.01}
        s.set_runtime_state(position=pos)
        assert s.position == pos

    def test_should_long_uses_data_dict(self):
        s = MomentumStrategy()
        assert s.should_long({"close": 3350, "ema_20": 3300}) is True
        assert s.should_long({"close": 3250, "ema_20": 3300}) is False

    def test_should_short_uses_data_dict(self):
        s = MomentumStrategy()
        assert s.should_short({"close": 3250, "ema_20": 3300}) is True
        assert s.should_short({"close": 3350, "ema_20": 3300}) is False

    def test_record_outcome_tracks_wins_losses(self):
        s = AdaptiveLossStrategy()
        trade_win = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
        )
        s.record_outcome(100.0, trade=trade_win)
        assert s.trades_taken == 1
        assert s.win_count == 1
        assert s.consecutive_losses == 0

        trade_loss = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        s.record_outcome(-50.0, trade=trade_loss)
        assert s.trades_taken == 2
        assert s.loss_count == 1
        assert s.consecutive_losses == 1

    def test_win_rate_calculation(self):
        s = MomentumStrategy()
        assert s.win_rate == 0.0  # no trades
        s.record_outcome(10.0)
        s.record_outcome(10.0)
        s.record_outcome(-5.0)
        assert s.win_rate == pytest.approx(2 / 3)

    def test_stats_dict(self):
        s = MomentumStrategy()
        stats = s.get_stats()
        assert "signals_generated" in stats
        assert "trades_taken" in stats
        assert "win_rate" in stats
        assert stats["name"] == "Momentum"


# ── 7. HyperparameterRange to_optuna_distribution ────────────────


class TestOptunaIntegration:
    def test_discrete_range(self):
        hp = HyperparameterRange("n_estimators", 50, 500, step=50)
        d = hp.to_optuna_distribution()
        assert d == {"low": 50, "high": 500, "step": 50}

    def test_continuous_range(self):
        hp = HyperparameterRange("lr", 0.001, 0.1)
        d = hp.to_optuna_distribution()
        assert d == {"low": 0.001, "high": 0.1}

    def test_log_range(self):
        hp = HyperparameterRange("lr", 1e-5, 1e-1, log=True)
        d = hp.to_optuna_distribution()
        assert d["log"] is True
        assert d["low"] == 1e-5

    def test_choices(self):
        hp = HyperparameterRange("method", 0, 0, choices=["ema", "sma", "wma", "dema"])
        d = hp.to_optuna_distribution()
        assert d["choices"] == ["ema", "sma", "wma", "dema"]
        assert "low" not in d  # choices don't need low/high

    def test_strategy_exposes_hyperparameters(self):
        s = OptunaReadyStrategy()
        hp = s.hyperparameters()
        assert len(hp) == 3
        for name in ["ema_fast", "ema_slow", "atr_mult"]:
            d = hp[name].to_optuna_distribution()
            assert "low" in d or "choices" in d

    def test_from_hyperparameters_applies_values(self):
        s = OptunaReadyStrategy()
        s.from_hyperparameters({"ema_fast": 12, "atr_mult": 2.2})
        assert s.ema_fast == 12
        assert s.atr_mult == 2.2
        assert s.ema_slow == 21  # unchanged


# ── 8. TradeResult creation and PnL ─────────────────────────────


class TestTradeResultPnL:
    def test_buy_profit(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.1"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
        )
        assert trade.pnl == Decimal("4.00")  # (3340-3300)*0.1
        assert trade.pnl > 0

    def test_buy_loss(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.1"),
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        assert trade.pnl == Decimal("-4.00")
        assert trade.pnl < 0

    def test_sell_profit(self):
        trade = Strategy.create_trade_result(
            symbol="EURUSD",
            side=OrderSide.SELL,
            entry_price=Decimal("1.1000"),
            exit_price=Decimal("1.0900"),
            quantity=Decimal("10000"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        assert trade.pnl == Decimal("100.00")  # (1.1-1.09)*10000

    def test_with_fees_reduces_pnl(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.1"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
            fees=Decimal("1.00"),
        )
        assert trade.pnl == Decimal("3.00")  # 4.00 - 1.00 fees

    def test_pnl_pct_calculation(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3333"),
            quantity=Decimal("0.1"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
        )
        assert trade.pnl_pct == pytest.approx(1.0, abs=0.01)

    def test_zero_price_risk(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.1"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        assert trade.pnl == Decimal("0.00")

    def test_on_trade_closed_adaptive_callback(self):
        s = AdaptiveLossStrategy()
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3290"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        s.record_outcome(float(trade.pnl), trade=trade)
        assert s.consecutive_losses == 1

    def test_consecutive_loss_tracking(self):
        s = AdaptiveLossStrategy()
        for _ in range(3):
            trade = Strategy.create_trade_result(
                symbol="XAUUSD",
                side=OrderSide.BUY,
                entry_price=Decimal("3300"),
                exit_price=Decimal("3290"),
                quantity=Decimal("0.01"),
                close_reason=CloseReason.STOP_LOSS,
                opened_at=datetime(2026, 1, 1),
                closed_at=datetime(2026, 1, 1),
            )
            s.record_outcome(float(trade.pnl), trade=trade)
        assert s.consecutive_losses == 3
        assert s.max_consecutive_losses_seen == 3


# ── 9. Backward compatibility ───────────────────────────────────


class TestBackwardCompatibility:
    def test_existing_mtm_strategy_works(self):
        from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum

        s = MultiTimeframeMomentum()
        assert s.id == "MultiTimeframeMomentum_2.0"
        assert s.should_long({}) is False
        assert s.supports_numba() is False
        assert s.hyperparameters() == {}
        stats = s.get_stats()
        assert "win_rate" in stats

    def test_strategy_config_defaults(self):
        cfg = StrategyConfig(name="Test")
        assert cfg.version == "1.0.0"
        assert cfg.risk_per_trade_pct == 1.0
        assert cfg.min_confidence == 0.60

    def test_signal_factory_method(self):
        sig = Signal.create(
            strategy_id="test_1",
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
        )
        assert sig.is_buy is True
        assert sig.is_sell is False
        assert sig.confidence == 0.9

    def test_signal_risk_reward_ratio(self):
        sig = Signal.create(
            strategy_id="test_1",
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
            take_profit=Decimal("3320"),
        )
        assert sig.risk_reward_ratio == pytest.approx(2.0)

    def test_signal_risk_reward_missing_levels(self):
        sig = Signal.create(
            strategy_id="test_1",
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
        )
        assert sig.risk_reward_ratio is None


# ── 10. Regime filtering integration ─────────────────────────────


class TestRegimeFiltering:
    def test_regime_strategy_trending_up(self):
        s = RegimeFilteredStrategy()
        assert s.is_valid_for_regime(RegimeType.TREND_STRONG_UP) is True

    def test_regime_strategy_range_bound(self):
        s = RegimeFilteredStrategy()
        assert s.is_valid_for_regime(RegimeType.RANGE_BOUND) is False

    def test_regime_strategy_generates_signal_only_in_valid_regime(self):
        s = RegimeFilteredStrategy()
        sig_up = s.generate_signal("XAUUSD", {"close": [3300]}, regime=RegimeType.TREND_STRONG_UP)
        assert sig_up is not None
        sig_range = s.generate_signal("XAUUSD", {"close": [3300]}, regime=RegimeType.RANGE_BOUND)
        assert sig_range is None

    def test_no_regime_filter_passes_all(self):
        s = MomentumStrategy()
        assert s.is_valid_for_regime(RegimeType.CRISIS) is True
        assert s.is_valid_for_regime(RegimeType.RANGE_BOUND) is True


# ── 11. Risk-aware strategy integration ──────────────────────────


class TestRiskAwareIntegration:
    def test_strategy_uses_balance_for_sizing(self):
        bus = EventBus()
        strategy = RiskAwareStrategy()
        signals = []

        def on_bar(bar: BarEvent):
            strategy.set_runtime_state(
                price=Decimal(str(bar.close)),
                balance=Decimal("10000"),
            )
            ohlcv = {"close": [bar.close]}
            sig = strategy.generate_signal(bar.symbol, ohlcv)
            if sig:
                signals.append(sig)

        bus.subscribe(BarEvent, on_bar)
        bus.publish(BarEvent(symbol="XAUUSD", close=3300.0))
        assert len(signals) == 1

    def test_no_signal_without_runtime_state(self):
        strategy = RiskAwareStrategy()
        sig = strategy.generate_signal("XAUUSD", {"close": [3300]})
        assert sig is None

    def test_position_size_calculation(self):
        s = MomentumStrategy()
        size = s.calculate_position_size(
            account_balance=Decimal("1000000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
        )
        assert size > Decimal("0")


# ── 12. Event bus + strategy + risk sizing pipeline ──────────────


class TestEndToEndPipeline:
    def test_full_bar_signal_order_fill_pipeline(self):
        bus = EventBus()
        strategy = MomentumStrategy()
        fills = []

        def on_bar(bar: BarEvent):
            ohlcv = {"close": [bar.close]}
            indicators = {"ema_20": 3300.0}
            sig = strategy.generate_signal(bar.symbol, ohlcv, indicators)
            if sig:
                bus.publish(
                    SignalEvent(
                        symbol=sig.symbol,
                        signal_type=sig.signal_type.value,
                        confidence=sig.confidence,
                    )
                )

        def on_signal(sig: SignalEvent):
            if sig.confidence >= 0.6:
                bus.publish(
                    OrderEvent(
                        symbol=sig.symbol,
                        side="BUY",
                        quantity=0.01,
                        strategy_id=strategy.id,
                    )
                )

        def on_order(ord: OrderEvent):
            bus.publish(
                FillEvent(
                    order_id=ord.order_id,
                    symbol=ord.symbol,
                    side=ord.side,
                    fill_price=3350.0,
                    fill_quantity=ord.quantity,
                )
            )

        def on_fill(fill: FillEvent):
            fills.append(fill)

        bus.subscribe(BarEvent, on_bar)
        bus.subscribe(SignalEvent, on_signal)
        bus.subscribe(OrderEvent, on_order)
        bus.subscribe(FillEvent, on_fill)

        bus.publish(BarEvent(symbol="XAUUSD", close=3350.0))
        assert len(fills) == 1
        assert fills[0].symbol == "XAUUSD"

    def test_kelly_sizes_order_from_tracker(self):
        tracker = TradeStatsTracker(window=100)
        for p in [100, 100, -50, 80, -30, 120]:
            tracker.record(p)

        f = kelly_fraction(
            win_rate=tracker.win_rate,
            avg_win=tracker.avg_win,
            avg_loss=tracker.avg_loss,
            fraction=0.25,
        )
        balance = Decimal("10000")
        risk_amount = balance * Decimal(str(f))
        price_risk = Decimal("10")  # entry - SL
        units = risk_amount / price_risk
        lots = units / Decimal("100000")
        assert lots >= Decimal("0")


# ── 13. KillSwitch and RegimeChange integration ──────────────────


class TestSystemEventsIntegration:
    def test_kill_switch_stops_all_trading(self):
        bus = EventBus()
        trading_active = [True]

        def on_kill(ks: KillSwitchEvent):
            trading_active[0] = False

        def on_bar(bar: BarEvent):
            if not trading_active[0]:
                return
            # would trade here

        bus.subscribe(KillSwitchEvent, on_kill)
        bus.subscribe(BarEvent, on_bar)

        bus.publish(BarEvent(symbol="XAUUSD", close=3300))
        assert trading_active[0] is True

        bus.publish(KillSwitchEvent(trigger="DAILY_LOSS", reason="exceeded 2%"))
        assert trading_active[0] is False

        # Subsequent bars should not trade
        bus.publish(BarEvent(symbol="XAUUSD", close=3350))
        assert trading_active[0] is False

    def test_regime_change_notifies_strategies(self):
        bus = EventBus()
        regime_changes = []

        def on_regime(rc: RegimeChangeEvent):
            regime_changes.append((rc.old_regime, rc.new_regime))

        bus.subscribe(RegimeChangeEvent, on_regime)
        bus.publish(
            RegimeChangeEvent(
                symbol="XAUUSD",
                old_regime="RANGE_BOUND",
                new_regime="TREND_STRONG_UP",
                confidence=0.85,
            )
        )
        assert len(regime_changes) == 1
        assert regime_changes[0] == ("RANGE_BOUND", "TREND_STRONG_UP")


# ── 14. Position sizer edge cases ───────────────────────────────


class TestPositionSizerEdgeCases:
    def test_fixed_fractional_zero_price_risk(self):
        sizer = FixedFractionalSizer(risk_pct=1.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3300"),
        )
        assert result.lots == Decimal("0")
        assert "Stop loss at entry" in result.notes

    def test_kelly_sizer_half_kelly(self):
        sizer = KellySizer(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
        )
        assert result.lots >= Decimal("0")
        assert "half-Kelly" in result.notes

    def test_atr_sizer_fallback_no_atr(self):
        sizer = ATRSizer(atr_multiple=1.5)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
        )
        assert "fallback" in result.method.lower()

    def test_anti_martingale_after_losses(self):
        sizer = AntiMartingaleSizer(base_risk_pct=1.0, consecutive_losses=3)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
        )
        assert result.lots >= Decimal("0")
        assert "0.25" in result.notes  # 25% adjustment

    def test_anti_martingale_after_wins(self):
        sizer = AntiMartingaleSizer(base_risk_pct=1.0, consecutive_wins=3)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("3300"),
            stop_loss=Decimal("3290"),
        )
        assert result.lots >= Decimal("0")

    def test_anti_martingale_record_outcome_streak(self):
        sizer = AntiMartingaleSizer(base_risk_pct=1.0)
        sizer.record_outcome(100)
        assert sizer.consecutive_wins == 1
        sizer.record_outcome(100)
        assert sizer.consecutive_wins == 2
        sizer.record_outcome(-50)
        assert sizer.consecutive_wins == 0
        assert sizer.consecutive_losses == 1
