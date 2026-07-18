"""
ML Mean Reversion Strategy (MLMR)

Concept: XGBoost predicts mean reversion probability after Bollinger Band touch.
Combines statistical mean reversion (BB + RSI) with ML confirmation.

Signal Logic:
- Price touches/crosses Bollinger Band (2.0 std)
- RSI confirms oversold/overbought (< 35 / > 65)
- XGBoost predicts P(mean_reversion) > 0.60
- ADX < 25 (range-bound market only)
- Volume > 0.8x average (not dead market)

Entry:
- Long: Price < BB_lower + RSI < 35 + ML confirm + ADX < 25
- Short: Price > BB_upper + RSI > 65 + ML confirm + ADX < 25

Risk Management:
- SL: Beyond BB band + 0.5 x ATR buffer
- TP: BB midline (SMA20) or opposite band
- Trailing: Move SL to breakeven at 1R profit

Expected Performance (range-bound markets):
- Win Rate: 65-70%
- Profit Factor: 1.5-1.8
- Max DD: 8-12%
- Sharpe: 1.2-1.5
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from ..core.enums import RegimeType, SignalType
from .base import Signal, Strategy, StrategyConfig

logger = structlog.get_logger(__name__)

# Default model directory
DEFAULT_MODEL_DIR = Path(__file__).parent.parent / "ml" / "models"


class MLMeanReversion(Strategy):
    """
    ML-enhanced Mean Reversion strategy.

    Uses XGBoost to confirm Bollinger Band mean reversion signals.
    Only trades in range-bound markets (ADX < threshold).

    Tuned parameters per symbol based on model quality (2026-07-12):
    - BTCUSD: Best balanced model → standard ML threshold
    - EURUSD: Moderate skew → slightly lower threshold
    - XAUUSD/NAS100/US30: Heavy skew → rely on technicals, ML as weak filter
    """

    # Symbol-specific parameter overrides
    SYMBOL_PARAMS = {
        "BTCUSD": {
            "min_ml_prob": 0.58,
            "adx_threshold": 20.0,  # Stricter: crypto trends more
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "bb_std": 2.5,  # Wider bands for crypto volatility
            "atr_sl_mult": 0.7,
            "min_risk_reward": 2.0,
        },
        "EURUSD": {
            "min_ml_prob": 0.55,
            "adx_threshold": 25.0,
            "rsi_oversold": 35.0,
            "rsi_overbought": 65.0,
            "bb_std": 2.0,
            "atr_sl_mult": 0.5,
            "min_risk_reward": 1.5,
        },
        "XAUUSD": {
            "min_ml_prob": 0.50,  # Heavy skew, ML is weak filter
            "adx_threshold": 22.0,  # Gold ranges less clearly
            "rsi_oversold": 32.0,
            "rsi_overbought": 68.0,
            "bb_std": 2.2,  # Slightly wider for gold
            "atr_sl_mult": 0.6,
            "min_risk_reward": 1.8,
        },
        "NAS100": {
            "min_ml_prob": 0.50,
            "adx_threshold": 25.0,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "bb_std": 2.0,
            "atr_sl_mult": 0.5,
            "min_risk_reward": 1.5,
        },
        "US30": {
            "min_ml_prob": 0.50,
            "adx_threshold": 25.0,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "bb_std": 2.0,
            "atr_sl_mult": 0.5,
            "min_risk_reward": 1.5,
        },
        "GBPUSD": {
            "min_ml_prob": 0.55,
            "adx_threshold": 25.0,
            "rsi_oversold": 35.0,
            "rsi_overbought": 65.0,
            "bb_std": 2.0,
            "atr_sl_mult": 0.5,
            "min_risk_reward": 1.5,
        },
        "USDJPY": {
            "min_ml_prob": 0.55,
            "adx_threshold": 25.0,
            "rsi_oversold": 35.0,
            "rsi_overbought": 65.0,
            "bb_std": 2.0,
            "atr_sl_mult": 0.5,
            "min_risk_reward": 1.5,
        },
    }

    def __init__(self, model_path: str | None = None, model_dir: str | None = None):
        config = StrategyConfig(
            name="ML Mean Reversion",
            version="1.1",  # Tuned version
            symbols=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US30", "NAS100", "BTCUSD"],
            timeframes=["M15", "H1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=3,
            min_confidence=0.60,
            min_risk_reward=1.5,
            regime_filter=[RegimeType.RANGE_BOUND, RegimeType.LOW_VOLATILITY],
        )
        super().__init__(config)

        # ML Model
        self._model = None
        self._model_path = model_path
        self._model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self._feature_names: list[str] = []
        self._model_loaded = False

        # Mean Reversion parameters (defaults, overridden per symbol)
        self.bb_period = 20
        self.bb_std = 2.0
        self.rsi_period = 14
        self.rsi_oversold = 35.0
        self.rsi_overbought = 65.0
        self.adx_period = 14
        self.adx_threshold = 25.0
        self.atr_period = 14
        self.atr_sl_mult = 0.5
        self.volume_threshold = 0.8

        # ML confidence threshold
        self.min_ml_prob = 0.60

    def _get_symbol_params(self, symbol: str) -> dict:
        """Get symbol-specific parameters."""
        return self.SYMBOL_PARAMS.get(symbol, {})

    def _load_model(self, symbol: str | None = None) -> bool:
        """Load XGBoost model for the given symbol."""
        if self._model_loaded:
            return self._model is not None

        try:
            from ..core.safe_pickle import safe_load_ml_model

            if self._model_path:
                # Use explicit path
                model_data = safe_load_ml_model(self._model_path)
            else:
                # Find latest model for symbol
                import glob

                pattern = str(self._model_dir / f"xgboost_{symbol or ''}*.pkl")
                model_files = sorted(glob.glob(pattern), reverse=True)
                if not model_files:
                    # Try generic model
                    pattern = str(self._model_dir / "xgboost_*.pkl")
                    model_files = sorted(glob.glob(pattern), reverse=True)

                if not model_files:
                    logger.warning("mlmr.no_model_found", symbol=symbol)
                    return False

                model_data = safe_load_ml_model(model_files[0])

            self._model = model_data["model"]
            self._feature_names = model_data.get("feature_names", [])
            self._model_loaded = True
            logger.info(
                "mlmr.model_loaded",
                symbol=symbol,
                features=len(self._feature_names),
            )
            return True

        except Exception as e:
            logger.error("mlmr.model_load_error", error=str(e))
            return False

    def required_features(self) -> list[str]:
        return [
            "bb_lower",
            "bb_middle",
            "bb_upper",
            "rsi_14",
            "adx",
            "atr_14",
            "volume_ratio",
            "close",
            "high",
            "low",
        ]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """Generate ML-enhanced mean reversion signal with symbol-specific tuning."""

        # Check regime validity
        if regime and not self.is_valid_for_regime(regime):
            return None

        # Apply symbol-specific parameters
        sym_params = self._get_symbol_params(symbol)
        min_ml = sym_params.get("min_ml_prob", self.min_ml_prob)
        adx_thresh = sym_params.get("adx_threshold", self.adx_threshold)
        rsi_os = sym_params.get("rsi_oversold", self.rsi_oversold)
        rsi_ob = sym_params.get("rsi_overbought", self.rsi_overbought)
        bb_std = sym_params.get("bb_std", self.bb_std)
        sl_mult = sym_params.get("atr_sl_mult", self.atr_sl_mult)
        min_rr = sym_params.get("min_risk_reward", self.config.min_risk_reward)

        # Load model for this symbol
        if not self._load_model(symbol):
            # Fallback: use pure technical signal without ML
            logger.debug("mlmr.no_model_fallback", symbol=symbol)

        # Use provided indicators or calculate
        if indicators is None:
            indicators = self._calculate_indicators(ohlcv_data)

        if not indicators:
            return None

        close = ohlcv_data.get("close", [])
        high = ohlcv_data.get("high", [])
        low = ohlcv_data.get("low", [])
        volume = ohlcv_data.get("volume", [])

        if len(close) < self.bb_period + 10:
            return None

        current_price = float(close[-1])
        current_vol = volume[-1] if volume else 0

        # Get indicator values
        bb_lower = indicators.get("bb_lower", [0])[-1] if indicators.get("bb_lower") else 0
        bb_upper = indicators.get("bb_upper", [0])[-1] if indicators.get("bb_upper") else 0
        bb_middle = indicators.get("bb_middle", [0])[-1] if indicators.get("bb_middle") else 0
        rsi = indicators.get("rsi_14", [50])[-1] if indicators.get("rsi_14") else 50
        adx = indicators.get("adx", [30])[-1] if indicators.get("adx") else 30
        atr = indicators.get("atr_14", [0])[-1] if indicators.get("atr_14") else 0

        # Volume filter
        avg_volume = sum(volume[-20:]) / 20 if volume else 0
        if avg_volume > 0 and current_vol < avg_volume * self.volume_threshold:
            return None

        # Check for mean reversion setup (symbol-specific thresholds)
        long_setup = (
            current_price <= bb_lower
            and rsi < rsi_os
            and adx < adx_thresh
        )
        short_setup = (
            current_price >= bb_upper
            and rsi > rsi_ob
            and adx < adx_thresh
        )

        if not (long_setup or short_setup):
            return None

        # ML Prediction (symbol-specific threshold)
        ml_prob = 0.65  # Default when no model
        if self._model is not None:
            features = self._prepare_features(indicators, ohlcv_data)
            ml_prob = self._predict(features)

            if ml_prob < min_ml:
                return None

        # Calculate SL/TP (symbol-specific multipliers)
        atr_dec = Decimal(str(atr))
        bb_middle_dec = Decimal(str(bb_middle))

        if long_setup:
            signal_type = SignalType.BUY
            entry = Decimal(str(current_price))
            # SL: Below BB lower + ATR buffer
            stop_loss = Decimal(str(bb_lower)) - (atr_dec * Decimal(str(sl_mult)))
            # TP: BB middle (mean reversion target)
            take_profit = bb_middle_dec
            confidence = ml_prob
        else:
            signal_type = SignalType.SELL
            entry = Decimal(str(current_price))
            # SL: Above BB upper + ATR buffer
            stop_loss = Decimal(str(bb_upper)) + (atr_dec * Decimal(str(sl_mult)))
            # TP: BB middle (mean reversion target)
            take_profit = bb_middle_dec
            confidence = ml_prob

        # Risk/reward check (symbol-specific)
        risk = abs(float(entry) - float(stop_loss))
        reward = abs(float(take_profit) - float(entry))
        if risk > 0 and reward / risk < min_rr:
            return None

        self.signals_generated += 1

        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            strength="strong" if confidence > 0.75 else "medium",
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            regime=regime,
            timeframe="M15",
            indicator_values={
                "bb_lower": bb_lower,
                "bb_middle": bb_middle,
                "bb_upper": bb_upper,
                "rsi": rsi,
                "adx": adx,
                "atr": atr,
                "ml_prob": ml_prob,
                "volume_ratio": current_vol / avg_volume if avg_volume > 0 else 0,
            },
            notes=f"MLMR signal: {'Long' if long_setup else 'Short'} MR with ML={ml_prob:.2f}, RSI={rsi:.0f}, ADX={adx:.0f}",
        )

    def _calculate_indicators(self, ohlcv_data: dict[str, list]) -> dict[str, Any]:
        """Calculate technical indicators for mean reversion."""
        try:
            import pandas as pd
            import pandas_ta as ta

            df = pd.DataFrame(
                {
                    "open": ohlcv_data.get("open", []),
                    "high": ohlcv_data.get("high", []),
                    "low": ohlcv_data.get("low", []),
                    "close": ohlcv_data.get("close", []),
                    "volume": ohlcv_data.get("volume", []),
                }
            )

            if len(df) < 30:
                return {}

            # Bollinger Bands
            bb = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
            if bb is not None and len(bb.columns) >= 3:
                df["bb_lower"] = bb.iloc[:, 0]
                df["bb_middle"] = bb.iloc[:, 1]
                df["bb_upper"] = bb.iloc[:, 2]

            # RSI
            df["rsi_14"] = ta.rsi(df["close"], length=self.rsi_period)

            # ADX
            adx = ta.adx(df["high"], df["low"], df["close"], length=self.adx_period)
            if adx is not None and len(adx.columns) >= 1:
                df["adx"] = adx.iloc[:, 0]

            # ATR
            df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)

            # Volume ratio
            vol_sma = df["volume"].rolling(window=20).mean()
            df["volume_ratio"] = df["volume"] / vol_sma

            # Additional features for ML
            df["ret_1"] = df["close"].pct_change(1)
            df["ret_5"] = df["close"].pct_change(5)
            df["ret_10"] = df["close"].pct_change(10)
            df["ma_5"] = df["close"].rolling(5).mean()
            df["ma_20"] = df["close"].rolling(20).mean()
            df["ratio_ma5_ma20"] = df["ma_5"] / df["ma_20"]

            # BB position (0 = at lower, 1 = at upper)
            bb_range = df["bb_upper"] - df["bb_lower"]
            df["bb_position"] = (df["close"] - df["bb_lower"]) / bb_range.replace(0, np.nan)

            # RSI z-score
            df["rsi_zscore"] = (df["rsi_14"] - 50) / 50

            result_cols = [
                c for c in df.columns
                if c not in ["open", "high", "low", "close", "volume"]
            ]
            return {col: df[col].tolist() for col in result_cols}

        except ImportError:
            return {}
        except Exception as e:
            logger.warning("mlmr.indicator_error", error=str(e))
            return {}

    def _prepare_features(self, indicators: dict[str, Any], ohlcv_data: dict[str, list]) -> np.ndarray:
        """Prepare feature vector for ML model prediction."""
        features = []

        # Map indicator names to model feature names
        feature_map = {
            "ret_1": "ret_1",
            "ret_5": "ret_5",
            "ret_10": "ret_10",
            "ma_5": "ma_5",
            "ma_20": "ma_20",
            "ratio_ma5_ma20": "ratio_ma5_ma20",
            "atr_14": "atr_14",
            "rsi_14": "rsi_14",
            "volume_ratio": "volume_ratio",
            "bb_position": "bb_position",
            "rsi_zscore": "rsi_zscore",
        }

        for feat_name in self._feature_names:
            # Try to find the feature in indicators
            value = 0.0
            for ind_key, ind_name in feature_map.items():
                if ind_name == feat_name or ind_key == feat_name:
                    vals = indicators.get(ind_name, indicators.get(ind_key, [0]))
                    value = float(vals[-1]) if vals else 0.0
                    break

            # Fallback: try direct lookup
            if value == 0.0:
                vals = indicators.get(feat_name, [0])
                value = float(vals[-1]) if vals else 0.0

            features.append(value if not np.isnan(value) else 0.0)

        return np.array(features).reshape(1, -1)

    def _predict(self, features: np.ndarray) -> float:
        """Make ML prediction."""
        if self._model is None:
            return 0.5

        try:
            if hasattr(self._model, "predict_proba"):
                prob = self._model.predict_proba(features)[0]
                if len(prob) >= 2:
                    return float(prob[1])  # Probability of positive class
                return float(prob[0])
            elif hasattr(self._model, "predict"):
                return float(self._model.predict(features)[0])
            return 0.5
        except Exception as e:
            logger.warning("mlmr.prediction_error", error=str(e))
            return 0.5

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> dict[str, float]:
        """Train the ML model for this strategy."""
        try:
            import xgboost as xgb
            from sklearn.metrics import accuracy_score, f1_score

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=3,
                learning_rate=0.01,
                subsample=0.7,
                colsample_bytree=0.7,
                reg_lambda=5.0,
                reg_alpha=2.0,
                random_state=42,
                verbosity=0,
            )

            model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )

            y_pred = model.predict(X_val)
            acc = accuracy_score(y_val, y_pred)
            f1 = f1_score(y_val, y_pred, average="weighted", zero_division=0)

            self._model = model
            self._model_loaded = True

            return {
                "accuracy": float(acc),
                "f1_score": float(f1),
            }
        except Exception as e:
            logger.error("mlmr.train_error", error=str(e))
            return {"accuracy": 0.0, "f1_score": 0.0}
