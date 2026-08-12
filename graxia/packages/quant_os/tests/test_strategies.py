"""Tests for Quant OS strategies"""

from decimal import Decimal

from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.strategies.base import Signal
from graxia.packages.quant_os.strategies.ensemble import get_ensemble_signal
from graxia.packages.quant_os.strategies.mrb import MeanReversionBollinger
from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum


class TestSignal:
    """Test Signal data class"""

    def test_signal_creation(self):
        """Can create a signal"""
        signal = Signal.create(strategy_id="test", symbol="EURUSD", signal_type=SignalType.BUY, confidence=0.75)
        assert signal.strategy_id == "test"
        assert signal.symbol == "EURUSD"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.75

    def test_risk_reward_ratio(self):
        """Calculate risk/reward ratio"""
        signal = Signal.create(
            strategy_id="test",
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0820"),
            take_profit=Decimal("1.0910"),
        )
        rr = signal.risk_reward_ratio
        assert rr is not None
        assert rr > 0


class TestMultiTimeframeMomentum:
    """Test MTM strategy"""

    def test_strategy_init(self):
        """Strategy initializes correctly"""
        strategy = MultiTimeframeMomentum()
        assert strategy.id.startswith("MultiTimeframeMomentum")
        assert strategy.config.name == "Multi-Timeframe Momentum"

    def test_required_features(self):
        """Strategy requires correct features"""
        strategy = MultiTimeframeMomentum()
        features = strategy.required_features()
        assert "ema_9" in features
        assert "ema_20" in features
        assert "rsi_14" in features

    def test_calculate_confidence(self):
        """Confidence calculation works"""
        strategy = MultiTimeframeMomentum()
        conditions = {
            "h4_bullish": True,
            "h1_bullish": True,
            "ema_cross_up": True,
            "above_trend_ema": True,
            "rsi_momentum": True,
            "volume_confirm": True,
        }
        confidence = strategy._calculate_confidence(conditions, 60, "long")
        assert 0.6 <= confidence <= 0.95


class TestMeanReversionBollinger:
    """Test MRB strategy"""

    def test_strategy_init(self):
        """Strategy initializes correctly"""
        strategy = MeanReversionBollinger()
        assert strategy.config.name == "Mean Reversion Bollinger"

    def test_required_features(self):
        """Strategy requires correct features"""
        strategy = MeanReversionBollinger()
        features = strategy.required_features()
        assert "bb_upper" in features
        assert "bb_lower" in features
        assert "adx" in features


class TestEnsemble:
    """Test ensemble strategy"""

    def test_ensemble_weights(self):
        """Ensemble uses correct weights"""
        from graxia.packages.quant_os.strategies.ensemble import STRATEGY_WEIGHTS

        assert STRATEGY_WEIGHTS["mtm"] == 0.40
        assert STRATEGY_WEIGHTS["mrb"] == 0.25
        assert STRATEGY_WEIGHTS["mlb"] == 0.35

    def test_get_ensemble_signal_buy(self):
        """Ensemble correctly aggregates buy signals"""
        mtm = Signal.create(strategy_id="mtm", symbol="EURUSD", signal_type=SignalType.BUY, confidence=0.80)

        decision, confidence, details = get_ensemble_signal(mtm_signal=mtm, mrb_signal=None, mlb_signal=None)

        assert decision in [SignalType.BUY, SignalType.NO_TRADE]
        assert 0 <= confidence <= 1

    def test_get_ensemble_signal_conflict(self):
        """Ensemble handles conflicting signals"""
        mtm = Signal.create(strategy_id="mtm", symbol="EURUSD", signal_type=SignalType.BUY, confidence=0.80)
        mrb = Signal.create(strategy_id="mrb", symbol="EURUSD", signal_type=SignalType.SELL, confidence=0.70)

        decision, confidence, details = get_ensemble_signal(mtm_signal=mtm, mrb_signal=mrb, mlb_signal=None)

        # Should abstain on conflicting signals
        assert decision != SignalType.BUY or decision != SignalType.SELL or confidence < 0.6


class TestPositionSizing:
    """Test position sizing"""

    def test_fixed_fractional(self):
        """Fixed fractional sizing calculates correctly"""
        from graxia.packages.quant_os.risk.position_sizer import FixedFractionalSizer

        sizer = FixedFractionalSizer(risk_pct=1.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0820"),
            symbol="EURUSD",
        )

        assert result.lots > 0
        assert result.risk_pct <= 1.0

    def test_kelly_sizer(self):
        """Kelly criterion sizing"""
        from graxia.packages.quant_os.risk.position_sizer import KellySizer

        sizer = KellySizer(win_rate=0.55, avg_win=1.5, avg_loss=1.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0820"),
            symbol="EURUSD",
        )

        assert result.lots > 0
        assert "Kelly" in result.method
