"""Tests for A1: Strategy helper methods (jesse-inspired ergonomics)"""

from datetime import datetime
from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.enums import CloseReason, OrderSide, SignalType
from graxia.packages.quant_os.strategies.base import HyperparameterRange, Signal, Strategy, TradeResult

# ── Test helpers ──────────────────────────────────────────────────


class SimpleStrategy(Strategy):
    """Minimal concrete strategy for testing base class"""

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class LongOnlyStrategy(Strategy):
    """Strategy that always wants long"""

    def should_long(self, data):
        return data.get("close", 0) > 100

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        if self.should_long({"close": ohlcv_data.get("close", [0])[-1]}):
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.8,
            )
        return None

    def required_features(self):
        return []


class AdaptiveStrategy(Strategy):
    """Strategy that adapts after losses"""

    def __init__(self):
        super().__init__()
        self.consecutive_losses = 0

    def on_trade_closed(self, trade):
        if trade.pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class HyperparamStrategy(Strategy):
    """Strategy with tunable hyperparameters"""

    def __init__(self):
        super().__init__()
        self.ema_fast = 9
        self.atr_mult = 1.5

    def hyperparameters(self):
        return {
            "ema_fast": HyperparameterRange("ema_fast", 5, 20, step=1),
            "atr_mult": HyperparameterRange("atr_mult", 1.0, 3.0, step=0.1),
        }

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class NumbaStrategy(Strategy):
    """Strategy that supports Numba"""

    def supports_numba(self):
        return True

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


# ── Tests: Convenience properties ────────────────────────────────


class TestConvenienceProperties:
    def test_price_default_none(self):
        s = SimpleStrategy()
        assert s.price is None

    def test_balance_default_none(self):
        s = SimpleStrategy()
        assert s.balance is None

    def test_position_default_none(self):
        s = SimpleStrategy()
        assert s.position is None

    def test_available_margin_default_none(self):
        s = SimpleStrategy()
        assert s.available_margin is None

    def test_set_runtime_state(self):
        s = SimpleStrategy()
        s.set_runtime_state(
            price=Decimal("3340.50"),
            balance=Decimal("5000"),
            position={"symbol": "XAUUSD", "side": "BUY"},
            available_margin=Decimal("4500"),
        )
        assert s.price == Decimal("3340.50")
        assert s.balance == Decimal("5000")
        assert s.position == {"symbol": "XAUUSD", "side": "BUY"}
        assert s.available_margin == Decimal("4500")

    def test_set_runtime_state_partial(self):
        s = SimpleStrategy()
        s.set_runtime_state(price=Decimal("100"))
        assert s.price == Decimal("100")
        assert s.balance is None  # unchanged


# ── Tests: Entry/exit helpers ────────────────────────────────────


class TestEntryExitHelpers:
    def test_should_long_default_false(self):
        s = SimpleStrategy()
        assert s.should_long({}) is False

    def test_should_short_default_false(self):
        s = SimpleStrategy()
        assert s.should_short({}) is False

    def test_should_long_override(self):
        s = LongOnlyStrategy()
        assert s.should_long({"close": 200}) is True
        assert s.should_long({"close": 50}) is False

    def test_should_long_used_by_generate_signal(self):
        s = LongOnlyStrategy()
        signal = s.generate_signal("XAUUSD", {"close": [200]})
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

        signal = s.generate_signal("XAUUSD", {"close": [50]})
        assert signal is None


# ── Tests: Lifecycle callbacks ────────────────────────────────────


class TestLifecycleCallbacks:
    def test_on_trade_closed_default_noop(self):
        s = SimpleStrategy()
        # Should not raise
        s.on_trade_closed(
            TradeResult(
                trade_id="t1",
                symbol="XAUUSD",
                side=OrderSide.BUY,
                entry_price=Decimal("3300"),
                exit_price=Decimal("3340"),
                quantity=Decimal("0.01"),
                pnl=Decimal("0.40"),
                pnl_pct=0.012,
                close_reason=CloseReason.TAKE_PROFIT,
                opened_at=datetime.utcnow(),
                closed_at=datetime.utcnow(),
            )
        )

    def test_on_trade_closed_adaptive(self):
        s = AdaptiveStrategy()
        assert s.consecutive_losses == 0

        # Win
        trade_win = TradeResult(
            trade_id="t1",
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.01"),
            pnl=Decimal("0.40"),
            pnl_pct=0.012,
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
        )
        s.on_trade_closed(trade_win)
        assert s.consecutive_losses == 0

        # Loss
        trade_loss = TradeResult(
            trade_id="t2",
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.01"),
            pnl=Decimal("-0.40"),
            pnl_pct=-0.012,
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
        )
        s.on_trade_closed(trade_loss)
        assert s.consecutive_losses == 1

        s.on_trade_closed(trade_loss)
        assert s.consecutive_losses == 2

        # Win resets
        s.on_trade_closed(trade_win)
        assert s.consecutive_losses == 0

    def test_record_outcome_fires_callback(self):
        s = AdaptiveStrategy()
        trade = TradeResult(
            trade_id="t3",
            symbol="XAUUSD",
            side=OrderSide.SELL,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.01"),
            pnl=Decimal("0.40"),
            pnl_pct=0.012,
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
        )
        s.record_outcome(0.40, trade=trade)
        assert s.trades_taken == 1
        assert s.consecutive_losses == 0  # win resets


# ── Tests: Hyperparameters ───────────────────────────────────────


class TestHyperparameters:
    def test_hyperparameters_default_empty(self):
        s = SimpleStrategy()
        assert s.hyperparameters() == {}

    def test_hyperparameters_override(self):
        s = HyperparamStrategy()
        hp = s.hyperparameters()
        assert "ema_fast" in hp
        assert "atr_mult" in hp
        assert hp["ema_fast"].low == 5
        assert hp["ema_fast"].high == 20
        assert hp["atr_mult"].step == 0.1

    def test_from_hyperparameters(self):
        s = HyperparamStrategy()
        s.from_hyperparameters({"ema_fast": 15, "atr_mult": 2.5})
        assert s.ema_fast == 15
        assert s.atr_mult == 2.5

    def test_from_hyperparameters_ignores_unknown(self):
        s = HyperparamStrategy()
        s.from_hyperparameters({"unknown_param": 42})
        # Should not raise

    def test_to_optuna_distribution(self):
        hp = HyperparameterRange("x", 1, 10, step=0.5)
        d = hp.to_optuna_distribution()
        assert d["low"] == 1
        assert d["high"] == 10
        assert d["step"] == 0.5

    def test_to_optuna_distribution_log(self):
        hp = HyperparameterRange("lr", 1e-5, 1e-1, log=True)
        d = hp.to_optuna_distribution()
        assert d["log"] is True

    def test_to_optuna_distribution_choices(self):
        hp = HyperparameterRange("method", 0, 0, choices=["ema", "sma", "wma"])
        d = hp.to_optuna_distribution()
        assert d["choices"] == ["ema", "sma", "wma"]


# ── Tests: Numba support ─────────────────────────────────────────


class TestNumbaSupport:
    def test_supports_numba_default_false(self):
        s = SimpleStrategy()
        assert s.supports_numba() is False

    def test_supports_numba_override(self):
        s = NumbaStrategy()
        assert s.supports_numba() is True


# ── Tests: TradeResult ───────────────────────────────────────────


class TestTradeResult:
    def test_create_trade_result_buy(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
        )
        assert trade.pnl == Decimal("0.40")  # (3340-3300) * 0.01
        assert trade.pnl_pct == pytest.approx(1.212, abs=0.01)  # percentage
        assert trade.symbol == "XAUUSD"
        assert trade.side == OrderSide.BUY

    def test_create_trade_result_sell(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.SELL,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        assert trade.pnl == Decimal("0.40")  # (3340-3300) * 0.01
        assert trade.side == OrderSide.SELL

    def test_create_trade_result_with_fees(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3300"),
            exit_price=Decimal("3340"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.TAKE_PROFIT,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 2),
            fees=Decimal("0.10"),
        )
        assert trade.pnl == Decimal("0.30")  # 0.40 - 0.10 fees

    def test_trade_result_loss(self):
        trade = Strategy.create_trade_result(
            symbol="XAUUSD",
            side=OrderSide.BUY,
            entry_price=Decimal("3340"),
            exit_price=Decimal("3300"),
            quantity=Decimal("0.01"),
            close_reason=CloseReason.STOP_LOSS,
            opened_at=datetime(2026, 1, 1),
            closed_at=datetime(2026, 1, 1),
        )
        assert trade.pnl == Decimal("-0.40")


# ── Tests: Backward compatibility ────────────────────────────────


class TestBackwardCompatibility:
    def test_mtm_still_works(self):
        from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum

        s = MultiTimeframeMomentum()
        assert s.id == "MultiTimeframeMomentum_2.0"
        assert s.should_long({}) is False
        assert s.supports_numba() is False
        assert s.hyperparameters() == {}

    def test_strategy_stats_unchanged(self):
        s = SimpleStrategy()
        stats = s.get_stats()
        assert "signals_generated" in stats
        assert "trades_taken" in stats
        assert "win_rate" in stats
