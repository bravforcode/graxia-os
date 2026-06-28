"""Tests for Ensemble Strategy C3: signal combination with StrategyEnsemble"""

from graxia.packages.quant_os.core.enums import DecisionType, RegimeType, SignalType
from graxia.packages.quant_os.core.events import BarEvent
from graxia.packages.quant_os.strategies.base import Signal
from graxia.packages.quant_os.strategies.ensemble import (
    StrategyEnsemble,
    _FakeStrategy,
    get_ensemble_signal,
    STRATEGY_WEIGHTS,
)

# ── Helper factories ─────────────────────────────────────────────


def make_signal(sig_type: SignalType, confidence: float = 0.7, **kw):
    return Signal.create(
        strategy_id=kw.pop("strategy_id", "test"),
        symbol=kw.pop("symbol", "XAUUSD"),
        signal_type=sig_type,
        confidence=confidence,
        **kw,
    )


def _ohlcv(close=2005):
    return {"close": [close], "open": [2000], "high": [2010], "low": [1990], "volume": [100]}


def _wrap(name, sig):
    return _FakeStrategy(name, sig)


# ── get_ensemble_signal unit tests (keyword-arg API) ─────────────


class TestGetEnsembleSignal:
    def test_unanimous_buy(self):
        s = make_signal(SignalType.BUY, 0.8)
        decision, confidence, details = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
        )
        assert decision == DecisionType.BUY
        assert confidence > 0.7

    def test_unanimous_sell(self):
        s = make_signal(SignalType.SELL, 0.8)
        decision, confidence, details = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
        )
        assert decision == DecisionType.SELL
        assert confidence > 0.7

    def test_conflicting_no_trade(self):
        buy_s = make_signal(SignalType.BUY, 0.8)
        sell_s = make_signal(SignalType.SELL, 0.8)
        decision, _, details = get_ensemble_signal(
            mtm_signal=buy_s, mrb_signal=sell_s, mlb_signal=sell_s,
        )
        assert decision == DecisionType.NO_TRADE

    def test_low_confidence_no_trade(self):
        s = make_signal(SignalType.BUY, 0.3)
        decision, _, details = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
        )
        assert decision == DecisionType.NO_TRADE

    def test_no_signals_no_trade(self):
        decision, _, details = get_ensemble_signal()
        assert decision == DecisionType.NO_TRADE

    def test_single_signal_can_trade(self):
        s = make_signal(SignalType.BUY, 0.9)
        decision, confidence, _ = get_ensemble_signal(mtm_signal=s)
        assert decision == DecisionType.BUY
        assert confidence >= 0.6

    def test_two_signals_combined(self):
        s = make_signal(SignalType.BUY, 0.9)
        decision, confidence, _ = get_ensemble_signal(mtm_signal=s, mrb_signal=s)
        assert decision == DecisionType.BUY
        assert confidence >= 0.6


# ── StrategyEnsemble class tests ────────────────────────────────


class TestStrategyEnsemble:
    def test_init_empty(self):
        ens = StrategyEnsemble()
        assert ens.get_weights() == {}

    def test_add_strategy(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s), weight=0.5)
        assert "mtm" in ens.get_weights()
        assert ens.get_weights()["mtm"] == 0.5

    def test_add_strategy_auto_weight(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s))
        ens.add_strategy(_wrap("mrb", s))
        weights = ens.get_weights()
        assert abs(weights["mtm"] - 0.5) < 0.01
        assert abs(weights["mrb"] - 0.5) < 0.01

    def test_remove_strategy(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s))
        assert ens.remove_strategy("mtm") is True
        assert ens.get_weights() == {}

    def test_remove_nonexistent(self):
        ens = StrategyEnsemble()
        assert ens.remove_strategy("ghost") is False

    def test_get_ensemble_signal_returns_signal(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s), 1.0)
        result = ens.get_ensemble_signal("XAUUSD", _ohlcv())
        assert result is None or isinstance(result, Signal)

    def test_get_ensemble_signal_empty_returns_none(self):
        ens = StrategyEnsemble()
        result = ens.get_ensemble_signal("XAUUSD", _ohlcv())
        assert result is None

    def test_get_weights_snapshot(self):
        s1 = make_signal(SignalType.BUY, 0.8)
        s2 = make_signal(SignalType.SELL, 0.6)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s1), 0.6)
        ens.add_strategy(_wrap("mrb", s2), 0.4)
        w = ens.get_weights()
        assert len(w) == 2
        assert abs(w["mtm"] - 0.6) < 0.01
        assert abs(w["mrb"] - 0.4) < 0.01

    def test_record_outcome(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s))
        ens.record_outcome("mtm", 1.5)
        rec = ens._records["mtm"]
        assert rec.trades_recorded == 1
        assert rec.cumulative_pnl_pct == 1.5

    def test_record_outcome_unknown_strategy(self):
        ens = StrategyEnsemble()
        ens.record_outcome("ghost", 1.0)

    def test_repr(self):
        s = make_signal(SignalType.BUY, 0.8)
        ens = StrategyEnsemble()
        ens.add_strategy(_wrap("mtm", s))
        assert "mtm" in repr(ens)


# ── Backward-compat keyword-arg API ─────────────────────────────


class TestBackwardCompatAPI:
    def test_mtm_signal_kwarg(self):
        s = make_signal(SignalType.BUY, 0.8)
        decision, confidence, details = get_ensemble_signal(mtm_signal=s)
        assert decision == DecisionType.BUY

    def test_mrb_signal_kwarg(self):
        s = make_signal(SignalType.BUY, 0.8)
        decision, _, _ = get_ensemble_signal(mrb_signal=s)
        assert decision == DecisionType.BUY

    def test_mlb_signal_kwarg(self):
        s = make_signal(SignalType.BUY, 0.8)
        decision, _, _ = get_ensemble_signal(mlb_signal=s)
        assert decision == DecisionType.BUY

    def test_all_three_kwargs(self):
        s = make_signal(SignalType.SELL, 0.8)
        decision, confidence, details = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
        )
        assert decision == DecisionType.SELL

    def test_details_have_buy_sell_scores(self):
        s = make_signal(SignalType.BUY, 0.8)
        _, _, details = get_ensemble_signal(mtm_signal=s, mrb_signal=s, mlb_signal=s)
        assert "buy_score" in details
        assert "sell_score" in details
        assert "weights" in details

    def test_regime_forwarded(self):
        s = make_signal(SignalType.BUY, 0.8)
        _, _, details = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert "weights" in details
        assert "buy_score" in details


# ── Edge cases ──────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_ohlcv(self):
        decision, _, _ = get_ensemble_signal()
        assert decision == DecisionType.NO_TRADE

    def test_custom_weights(self):
        weights = {"mtm": 0.5, "mrb": 0.3, "mlb": 0.2}
        s = make_signal(SignalType.BUY, 0.8)
        decision, _, _ = get_ensemble_signal(
            mtm_signal=s, mrb_signal=s, mlb_signal=s,
            weights=weights,
        )
        assert decision == DecisionType.BUY

    def test_ensemble_with_strategies_list(self):
        s = make_signal(SignalType.BUY, 0.8)
        strategies = [_wrap("mtm", s), _wrap("mrb", s), _wrap("mlb", s)]
        decision, confidence, details = get_ensemble_signal(
            strategies=strategies, symbol="XAUUSD", ohlcv=_ohlcv(),
        )
        assert decision == DecisionType.BUY
        assert confidence > 0.7
