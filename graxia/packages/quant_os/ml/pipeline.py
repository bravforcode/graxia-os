"""
ML Pipeline - Feature engineering and model training for MLB strategy

Handles:
- Feature engineering from OHLCV data
- Label generation (future returns)
- Model training (XGBoost, LightGBM, RandomForest)
- Model evaluation with walk-forward
- Drift detection
- Model versioning and persistence
"""

import os
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from graxia.packages.quant_os.core.safe_pickle import safe_load_model


@dataclass
class FeatureSet:
    """Feature matrix with metadata"""

    features: list[dict[str, float]]
    labels: list[int]  # 0 = no trade, 1 = buy, 2 = sell
    timestamps: list[datetime]
    feature_names: list[str]
    symbol: str = ""
    timeframe: str = "M15"


@dataclass
class ModelResult:
    """ML model training result"""

    model_name: str
    version: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    oos_accuracy: float = 0.0
    feature_importance: dict[str, float] = field(default_factory=dict)
    trained_at: datetime = field(default_factory=datetime.utcnow)
    model_path: str = ""
    feature_list: list[str] = field(default_factory=list)
    training_samples: int = 0
    is_trained: bool = False


class FeatureEngineer:
    """
    Generate features from OHLCV data for ML models.

    Features include:
    - Price-based: returns, log returns, price position
    - Technical: RSI, MACD, Bollinger, ATR, ADX
    - Volume: volume ratio, OBV trend
    - Volatility: realized vol, ATR ratio
    - Pattern: candle patterns, engulfing
    """

    def __init__(self):
        self.feature_names: list[str] = []

    def generate_features(
        self,
        ohlcv_data: dict[str, list],
        timestamps: list[datetime] | None = None,
    ) -> FeatureSet:
        """
        Generate feature matrix from OHLCV data.

        Args:
            ohlcv_data: Dict with 'open', 'high', 'low', 'close', 'volume'
            timestamps: Optional timestamps

        Returns:
            FeatureSet with features and labels
        """
        import numpy as np
        import pandas as pd
        import pandas_ta as ta

        df = pd.DataFrame(ohlcv_data)

        if len(df) < 300:
            raise ValueError(f"Insufficient data: {len(df)} bars. Need at least 300.")

        features = pd.DataFrame(index=df.index)

        # === Price Features ===
        features["return_1"] = df["close"].pct_change(1)
        features["return_5"] = df["close"].pct_change(5)
        features["return_10"] = df["close"].pct_change(10)
        features["return_20"] = df["close"].pct_change(20)

        features["log_return_1"] = (df["close"] / df["close"].shift(1)).apply(
            lambda x: __import__("math").log(x) if x > 0 else 0
        )

        # Price position in range
        features["price_position_20"] = (df["close"] - df["low"].rolling(20).min()) / (
            df["high"].rolling(20).max() - df["low"].rolling(20).min() + 1e-10
        )

        # === Moving Average Features ===
        for period in [9, 20, 50, 200]:
            ema = ta.ema(df["close"], length=period)
            if ema is not None:
                features[f"ema_{period}_dist"] = (df["close"] - ema) / ema

        # EMA crosses
        ema_9 = ta.ema(df["close"], length=9)
        ema_20 = ta.ema(df["close"], length=20)
        if ema_9 is not None and ema_20 is not None:
            features["ema_cross_9_20"] = (ema_9 - ema_20) / ema_20

        # === RSI ===
        rsi = ta.rsi(df["close"], length=14)
        if rsi is not None:
            features["rsi_14"] = rsi
            features["rsi_14_normalized"] = (rsi - 50) / 50

        # === MACD ===
        macd = ta.macd(df["close"])
        if macd is not None and len(macd.columns) >= 3:
            features["macd"] = macd.iloc[:, 0]
            features["macd_signal"] = macd.iloc[:, 1]
            features["macd_hist"] = macd.iloc[:, 2]

        # === Bollinger Bands ===
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and len(bb.columns) >= 3:
            bb_upper = bb.iloc[:, 2]
            bb_lower = bb.iloc[:, 0]
            bb_mid = bb.iloc[:, 1]
            features["bb_width"] = (bb_upper - bb_lower) / bb_mid
            features["bb_position"] = (df["close"] - bb_lower) / (bb_upper - bb_lower + 1e-10)

        # === ATR ===
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr is not None:
            features["atr_14"] = atr
            features["atr_ratio"] = atr / df["close"]

        # === ADX ===
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is not None and len(adx.columns) >= 1:
            features["adx"] = adx.iloc[:, 0]

        # === Volume Features ===
        vol_sma = df["volume"].rolling(20).mean()
        features["volume_ratio"] = df["volume"] / (vol_sma + 1e-10)
        features["volume_change"] = df["volume"].pct_change(1)

        # OBV trend
        obv = ta.obv(df["close"], df["volume"])
        if obv is not None:
            obv_sma = obv.rolling(20).mean()
            features["obv_trend"] = (obv - obv_sma) / (obv_sma.abs() + 1e-10)

        # === Volatility Features ===
        features["realized_vol_20"] = df["close"].pct_change().rolling(20).std() * (252**0.5)
        features["realized_vol_5"] = df["close"].pct_change().rolling(5).std() * (252**0.5)
        features["vol_ratio"] = features["realized_vol_5"] / (features["realized_vol_20"] + 1e-10)

        # Garman-Klass Volatility (rolling) — captures intra-bar OHLC noise
        # np.maximum guards against floating-point negative variance
        # .shift(1) prevents data leakage — vol at bar t uses data up to t-1 only
        # Annualization: sqrt(252 * 23) ≈ sqrt(5796) for 1H bars (252 days × 23 hours)
        log_hl = np.log(df["high"] / df["low"])
        log_co = np.log(df["close"] / df["open"])
        raw_gk_var = np.maximum(0.0, 0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2)
        _annualize_1h = np.sqrt(252 * 23)  # ≈ 76.13
        features["gk_vol_14"] = np.sqrt(raw_gk_var.rolling(window=14).mean()).shift(1) * _annualize_1h
        features["gk_vol_20"] = np.sqrt(raw_gk_var.rolling(window=20).mean()).shift(1) * _annualize_1h

        # Parkinson Volatility (rolling) — uses High-Low range only
        raw_park_var = (1 / (4 * np.log(2))) * log_hl**2
        features["parkinson_vol_14"] = np.sqrt(raw_park_var.rolling(window=14).mean()).shift(1) * _annualize_1h

        # === Candle Features ===
        body = df["close"] - df["open"]
        range_ = df["high"] - df["low"]
        features["candle_body_ratio"] = body / (range_ + 1e-10)
        features["upper_shadow"] = (df["high"] - df[["close", "open"]].max(axis=1)) / (range_ + 1e-10)
        features["lower_shadow"] = (df[["close", "open"]].min(axis=1) - df["low"]) / (range_ + 1e-10)

        # === Momentum Features ===
        features["momentum_10"] = df["close"] - df["close"].shift(10)
        features["momentum_20"] = df["close"] - df["close"].shift(20)

        # Stochastic
        stoch = ta.stoch(df["high"], df["low"], df["close"])
        if stoch is not None and len(stoch.columns) >= 2:
            features["stoch_k"] = stoch.iloc[:, 0]
            features["stoch_d"] = stoch.iloc[:, 1]

        # Clean up
        features = features.replace([float("inf"), float("-inf")], 0)
        features = features.fillna(0)

        # Store feature names
        self.feature_names = list(features.columns)

        # Generate labels using triple-barrier method (López de Prado)
        # Replace naive ±0.5% threshold with proper TP/SL/timeout labeling.
        # ATR must already be on df for triple_barrier to use.
        df["atr_14"] = features["atr_14"] if "atr_14" in features else df["close"].rolling(14).std()

        from .labeling import compute_triple_barrier

        labels = compute_triple_barrier(df, tp_mult=1.5, sl_mult=1.0, max_bars=12, atr_col="atr_14")
        _barrier_max_bars = 12  # must match compute_triple_barrier's max_bars

        # Trim to valid range (remove NaN from both ends)
        valid_start = 300  # Need history for indicators
        valid_end = len(df) - _barrier_max_bars  # Need forward bars for triple barrier

        feature_list = features.iloc[valid_start:valid_end].to_dict("records")
        label_list = labels[valid_start:valid_end].tolist()
        ts_list = timestamps[valid_start:valid_end] if timestamps else [datetime.now(UTC)] * len(label_list)

        return FeatureSet(
            features=feature_list,
            labels=label_list,
            timestamps=ts_list,
            feature_names=self.feature_names,
        )

    def _classify_returns(self, forward_returns, buy_threshold: float = 0.005, sell_threshold: float = -0.005):
        """DEPRECATED: Use ``compute_triple_barrier()`` from ``ml.labeling`` instead.

        Naive ±0.5% threshold classifier — remains as reference/fallback only.
        ``generate_features()`` now uses triple-barrier labeling for proper
        TP/SL/timeout classification (López de Prado method).
        """
        import pandas as pd

        labels = pd.Series(0, index=forward_returns.index)  # 0 = hold
        labels[forward_returns > buy_threshold] = 1  # 1 = buy
        labels[forward_returns < sell_threshold] = 2  # 2 = sell
        return labels


class MLTrainer:
    """
    Train ML models for signal prediction.

    Supports:
    - XGBoost
    - LightGBM
    - RandomForest
    - Walk-forward training
    """

    def __init__(self, model_dir: str = "./ml/models"):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

    def train(
        self,
        feature_set: FeatureSet,
        model_type: str = "xgboost",
        test_ratio: float = 0.2,
        registry: Any | None = None,
    ) -> ModelResult:
        """
        Train a model on the given feature set.

        Args:
            feature_set: Features and labels
            model_type: "xgboost", "lightgbm", "random_forest"
            test_ratio: Hold-out test ratio
            registry: Optional ml.model_registry.ModelRegistry instance. If
                provided, the trained model is ALSO registered there (in
                addition to the existing pickle save below, which is left
                unchanged for backward compatibility). Registration computes
                a feature_list_hash via the same canonical algorithm used by
                the live inference path (ml.feature_store.compute_feature_list_hash),
                so any consumer that loads this model through the registry can
                fail closed on a feature/model contract mismatch. Registration
                failures are logged and swallowed — they must never block
                training from completing.

        Returns:
            ModelResult with metrics
        """
        import numpy as np
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

        X = np.array([list(f.values()) for f in feature_set.features])
        y = np.array(feature_set.labels)

        # Purge/embargo split: reserve a gap of 12 bars between train and test
        # to prevent label leakage through the triple-barrier forward window.
        # Without this, the last N training labels peek into the test set's
        # forward returns (look-ahead bias).
        _gap = 12  # must match triple_barrier max_bars
        split_idx = int(len(X) * (1.0 - test_ratio))
        test_start = split_idx + _gap  # skip the leakage window

        if test_start >= len(X):
            # Not enough data for purge gap — use standard split as fallback
            test_start = max(split_idx, int(len(X) * 0.5))

        X_train, y_train = X[:split_idx], y[:split_idx]
        X_test, y_test = X[test_start:], y[test_start:]

        # Train model
        model = self._create_model(model_type)

        # Configure early stopping at fit-time (avoid constructor/eval_metric conflicts)
        n_classes = len(set(y))
        if hasattr(model, "set_params"):
            if model_type == "xgboost":
                model.set_params(
                    early_stopping_rounds=10,
                    eval_metric="mlogloss" if n_classes > 2 else "logloss",
                )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        # Evaluate
        y_pred = model.predict(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
        recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)
        f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)

        # Feature importance
        feature_importance = {}
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            for name, imp in zip(feature_set.feature_names, importances, strict=False):
                feature_importance[name] = float(imp)

        # Save model
        version = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        model_path = os.path.join(self.model_dir, f"{model_type}_{version}.pkl")

        with open(model_path, "wb") as f:
            pickle.dump(
                {
                    "model": model,
                    "feature_names": feature_set.feature_names,
                    "model_type": model_type,
                    "version": version,
                },
                f,
            )

        if registry is not None:
            try:
                registry.register_model(
                    model,
                    model_name=f"{model_type}_{feature_set.symbol or 'unknown'}",
                    model_type=model_type,
                    symbol=feature_set.symbol,
                    timeframe=feature_set.timeframe,
                    feature_list=feature_set.feature_names,
                    metrics={
                        "accuracy": float(accuracy),
                        "precision": float(precision),
                        "recall": float(recall),
                        "f1_score": float(f1),
                    },
                    training_samples=len(X_train),
                )
            except Exception as exc:  # noqa: BLE001 — registration is best-effort, never blocks training
                import logging

                logging.getLogger(__name__).warning("model_registry_registration_failed: %s", exc)

        return ModelResult(
            model_name=model_type,
            version=version,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            feature_importance=feature_importance,
            model_path=model_path,
            feature_list=feature_set.feature_names,
            training_samples=len(X_train),
            is_trained=True,
        )

    def train_walk_forward(
        self,
        feature_set: FeatureSet,
        model_type: str = "xgboost",
        n_windows: int = 3,
    ) -> list[ModelResult]:
        """
        Walk-forward training for robust evaluation.

        Args:
            feature_set: Full feature set
            model_type: Model type
            n_windows: Number of walk-forward windows

        Returns:
            List of ModelResult for each OOS window
        """
        total = len(feature_set.features)
        window_size = total // (n_windows + 1)

        results = []

        # Purge gap: must match triple_barrier max_bars (12) to prevent
        # label leakage through the forward-looking window.
        _gap = 12

        for w in range(n_windows):
            is_end = window_size * (w + 2)
            oos_start = is_end + _gap  # skip the leakage window
            oos_end = min(oos_start + window_size, total)

            if oos_end <= oos_start:
                break

            # IS data (excludes purge gap)
            is_features = feature_set.features[:is_end]
            is_labels = feature_set.labels[:is_end]

            # OOS data (starts after purge gap)
            oos_features = feature_set.features[oos_start:oos_end]
            oos_labels = feature_set.labels[oos_start:oos_end]

            # Train on IS
            is_set = FeatureSet(
                features=is_features,
                labels=is_labels,
                timestamps=feature_set.timestamps[:is_end],
                feature_names=feature_set.feature_names,
            )

            result = self.train(is_set, model_type, test_ratio=0.1)

            # Evaluate on OOS
            if oos_features:
                import numpy as np
                from sklearn.metrics import accuracy_score

                with open(result.model_path, "rb") as f:
                    model_data = safe_load_model(result.model_path)
                model = model_data["model"]

                X_oos = np.array([list(f.values()) for f in oos_features])
                y_oos = np.array(oos_labels)
                y_pred = model.predict(X_oos)

                result.oos_accuracy = accuracy_score(y_oos, y_pred)

            results.append(result)

        return results

    def _create_model(self, model_type: str):
        """Create ML model instance"""
        if model_type == "xgboost":
            from xgboost import XGBClassifier

            return XGBClassifier(
                n_estimators=200,
                max_depth=3,
                learning_rate=0.01,
                subsample=0.7,
                colsample_bytree=0.7,
                reg_lambda=5.0,
                reg_alpha=2.0,
                random_state=42,
            )
        elif model_type == "lightgbm":
            from lightgbm import LGBMClassifier

            return LGBMClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                verbose=-1,
            )
        elif model_type == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1,
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def load_model(self, model_path: str) -> dict[str, Any]:
        """Load a trained model"""
        return safe_load_model(model_path)

    def predict(self, model_path: str, features: dict[str, float]) -> tuple[int, float]:
        """
        Predict signal from features.

        Returns:
            Tuple of (signal_class, confidence)
        """
        import numpy as np

        model_data = self.load_model(model_path)
        model = model_data["model"]
        feature_names = model_data["feature_names"]

        # Order features
        feature_values = [features.get(name, 0) for name in feature_names]
        X = np.array([feature_values])

        # Predict
        prediction = model.predict(X)[0]
        probabilities = model.predict_proba(X)[0]
        confidence = float(max(probabilities))

        return int(prediction), confidence

    def predict_payload(
        self,
        model_path: str,
        features: dict[str, float],
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ):
        """Predict and return canonical MLSignalPayload (Pydantic v2)."""
        try:
            from core.canonical.payloads import MLSignalPayload, SignalDirection
        except ImportError:
            from graxia.packages.quant_os.core.canonical.payloads import MLSignalPayload, SignalDirection

        prediction, confidence = self.predict(model_path, features)
        direction_map = {0: SignalDirection.HOLD, 1: SignalDirection.BUY, 2: SignalDirection.SELL}
        direction = direction_map.get(prediction, SignalDirection.HOLD)
        model_version = model_path.split("/")[-1].replace(".pkl", "")

        return MLSignalPayload(
            symbol=symbol,
            xgb_probability=confidence,
            xgb_model_version=model_version,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


class DriftDetector:
    """
    Detect model drift by monitoring prediction accuracy over time.
    """

    def __init__(self, window_size: int = 100, threshold: float = 0.10):
        self.window_size = window_size
        self.threshold = threshold
        self.history: list[tuple[int, int]] = []  # (predicted, actual)

    def record(self, predicted: int, actual: int) -> None:
        """Record a prediction vs actual"""
        self.history.append((predicted, actual))
        if len(self.history) > self.window_size * 2:
            self.history = self.history[-self.window_size * 2 :]

    def check_drift(self) -> dict[str, Any]:
        """
        Check if model has drifted.

        Returns:
            Dict with drift status and metrics
        """
        if len(self.history) < self.window_size:
            return {"drifted": False, "reason": "insufficient_data", "samples": len(self.history)}

        # Recent accuracy
        recent = self.history[-self.window_size :]
        recent_correct = sum(1 for p, a in recent if p == a)
        recent_accuracy = recent_correct / len(recent)

        # Historical accuracy
        historical = self.history[: -self.window_size]
        if historical:
            hist_correct = sum(1 for p, a in historical if p == a)
            hist_accuracy = hist_correct / len(historical)
        else:
            hist_accuracy = recent_accuracy

        # Check drift
        accuracy_drop = hist_accuracy - recent_accuracy
        drifted = accuracy_drop > self.threshold

        return {
            "drifted": drifted,
            "recent_accuracy": recent_accuracy,
            "historical_accuracy": hist_accuracy,
            "accuracy_drop": accuracy_drop,
            "threshold": self.threshold,
            "samples": len(self.history),
            "recommendation": "retrain" if drifted else "continue",
        }
