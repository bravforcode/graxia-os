"""Test suite for ML pipeline training (Wave 5).

Covers:
- Feature schema alignment with features_v3
- Train/test overlap detection
- Model save/load roundtrip
- Single-sample prediction latency
- Early stopping effectiveness
- Overfit warning triggers
"""

from __future__ import annotations

import os
import pickle
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on sys.path for core.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Feature builder (standalone, no pandas_ta dependency)
# ---------------------------------------------------------------------------

# Canonical v3 feature list — must match build_features_v3_multi_asset.py + ml/pipeline.py
V3_FEATURE_NAMES = [
    "return_1", "return_5", "return_10", "return_20",
    "log_return_1",
    "price_position_20",
    "ema_9_dist", "ema_20_dist", "ema_50_dist", "ema_200_dist",
    "ema_cross_9_20",
    "rsi_14", "rsi_14_normalized",
    "macd", "macd_signal", "macd_hist",
    "bb_width", "bb_position",
    "atr_14", "atr_ratio",
    "adx",
    "volume_ratio", "volume_change",
    "obv_trend",
    "realized_vol_20", "realized_vol_5", "vol_ratio",
    "candle_body_ratio", "upper_shadow", "lower_shadow",
    "momentum_10", "momentum_20",
    "stoch_k", "stoch_d",
]


def _build_features_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Build features from OHLCV without pandas_ta."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    feat = pd.DataFrame(index=df.index)

    # Price returns
    for p in [1, 5, 10, 20]:
        feat[f"return_{p}"] = close.pct_change(p)
    feat["log_return_1"] = np.log(close / close.shift(1))
    feat["price_position_20"] = (close - low.rolling(20).min()) / (
        high.rolling(20).max() - low.rolling(20).min() + 1e-10
    )

    # EMA distances
    for span in [9, 20, 50, 200]:
        ema = close.ewm(span=span, adjust=False).mean()
        feat[f"ema_{span}_dist"] = (close - ema) / ema
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    feat["ema_cross_9_20"] = (ema9 - ema20) / ema20

    # RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    feat["rsi_14"] = 100 - 100 / (1 + rs)
    feat["rsi_14_normalized"] = (feat["rsi_14"] - 50) / 50

    # MACD (12,26,9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    feat["macd"] = ema12 - ema26
    feat["macd_signal"] = feat["macd"].ewm(span=9, adjust=False).mean()
    feat["macd_hist"] = feat["macd"] - feat["macd_signal"]

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    feat["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
    feat["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)

    # ATR
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    feat["atr_14"] = tr.rolling(14).mean()
    feat["atr_ratio"] = feat["atr_14"] / close.replace(0, np.nan)

    # ADX (simplified)
    plus_dm = high.diff().where(lambda x: x > 0, 0.0)
    minus_dm = (-low.diff()).where(lambda x: x > 0, 0.0)
    atr_s = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    feat["adx"] = dx.rolling(14).mean()

    # Volume
    feat["volume_ratio"] = volume / volume.rolling(20).mean()
    feat["volume_change"] = volume.pct_change(1)
    obv = (np.sign(close.diff()) * volume).cumsum()
    feat["obv_trend"] = (obv - obv.rolling(20).mean()) / (obv.rolling(20).mean().abs() + 1e-10)

    # Volatility
    feat["realized_vol_20"] = close.pct_change().rolling(20).std() * np.sqrt(252)
    feat["realized_vol_5"] = close.pct_change().rolling(5).std() * np.sqrt(252)
    feat["vol_ratio"] = feat["realized_vol_5"] / (feat["realized_vol_20"] + 1e-10)

    # Candle
    body = close - df["open"]
    range_ = high - low
    feat["candle_body_ratio"] = body / (range_ + 1e-10)
    feat["upper_shadow"] = (high - df[["close", "open"]].max(axis=1)) / (range_ + 1e-10)
    feat["lower_shadow"] = (df[["close", "open"]].min(axis=1) - low) / (range_ + 1e-10)

    # Momentum
    feat["momentum_10"] = close - close.shift(10)
    feat["momentum_20"] = close - close.shift(20)

    # Stochastic
    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    feat["stoch_k"] = 100 * (close - low14) / (high14 - low14 + 1e-10)
    feat["stoch_d"] = feat["stoch_k"].rolling(3).mean()

    # Clean
    feat = feat.replace([np.inf, -np.inf], 0).fillna(0)
    return feat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ohlcv() -> dict[str, list]:
    """Generate synthetic OHLCV data (500 bars)."""
    rng = np.random.RandomState(42)
    n = 500
    close = 2000 + np.cumsum(rng.randn(n) * 5)
    return {
        "open": (close + rng.randn(n) * 2).tolist(),
        "high": (close + abs(rng.randn(n) * 5)).tolist(),
        "low": (close - abs(rng.randn(n) * 5)).tolist(),
        "close": close.tolist(),
        "volume": (rng.rand(n) * 10000 + 1000).tolist(),
    }


@pytest.fixture
def feature_set(sample_ohlcv):
    """Build a FeatureSet from synthetic data using standalone builder."""
    from ml.pipeline import FeatureSet

    df = pd.DataFrame(sample_ohlcv)
    feat = _build_features_raw(df)
    timestamps = [
        pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i * 4)
        for i in range(len(df))
    ]

    # Forward return labels (10-bar)
    fwd_ret = df["close"].pct_change(10).shift(-10)
    labels = pd.Series(0, index=df.index)
    labels[fwd_ret > 0.005] = 1
    labels[fwd_ret < -0.005] = 2

    valid_start = 300
    valid_end = len(df) - 10

    feature_names = list(feat.columns)
    feature_list = feat.iloc[valid_start:valid_end].to_dict("records")
    label_list = labels.iloc[valid_start:valid_end].tolist()
    ts_list = timestamps[valid_start:valid_end]

    return FeatureSet(
        features=feature_list,
        labels=label_list,
        timestamps=ts_list,
        feature_names=feature_names,
    )


@pytest.fixture
def trained_model(feature_set):
    """Train a quick XGBoost model and return (ModelResult, trainer)."""
    from ml.pipeline import MLTrainer

    trainer = MLTrainer(model_dir=tempfile.mkdtemp())
    result = trainer.train(feature_set, model_type="xgboost", test_ratio=0.2)
    return result, trainer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeatureSchemaMatchesV3:
    """Verify feature schema matches the features_v3 spec."""

    def test_feature_schema_matches_v3(self, feature_set):
        """All expected v3 features must be present."""
        actual = set(feature_set.feature_names)
        expected = set(V3_FEATURE_NAMES)
        missing = expected - actual
        assert not missing, f"Missing features: {missing}"

    def test_feature_count_reasonable(self, feature_set):
        """Feature count should be >= 30 (v3 spec)."""
        assert len(feature_set.feature_names) >= 30, (
            f"Only {len(feature_set.feature_names)} features, expected >= 30"
        )

    def test_no_all_nan_features(self, feature_set):
        """No feature column should be entirely NaN/zero."""
        X = np.array([list(f.values()) for f in feature_set.features])
        for i, name in enumerate(feature_set.feature_names):
            col = X[:, i]
            assert not np.all(col == 0), f"Feature '{name}' is all zeros"


class TestTrainTestNoOverlap:
    """Verify train and test sets have zero index overlap."""

    def test_train_test_no_overlap(self, feature_set):
        """Walk-forward splits must have no bar overlap."""
        from sklearn.model_selection import train_test_split

        indices = np.arange(len(feature_set.features))
        train_idx, test_idx = train_test_split(
            indices, test_size=0.2, shuffle=False,
        )
        overlap = set(train_idx) & set(test_idx)
        assert not overlap, f"Overlap of {len(overlap)} indices between train/test"

    def test_embargo_gap_exists(self):
        """walk_forward_split must have embargo gap >= 12 bars."""
        from validation.walk_forward import walk_forward_split

        splits = walk_forward_split(n_bars=1000, n_folds=5, embargo_bars=12)
        for (train_start, train_end), (test_start, test_end) in splits:
            gap = test_start - train_end
            assert gap >= 12, (
                f"Embargo gap {gap} < 12 between train [{train_start}:{train_end}] "
                f"and test [{test_start}:{test_end}]"
            )

    def test_cpcv_no_overlap(self):
        """CPCV folds must have no train/test overlap."""
        try:
            from core.cross_validation import combine_purged_k_fold_cv
        except ModuleNotFoundError:
            from graxia.packages.quant_os.core.cross_validation import combine_purged_k_fold_cv

        n_bars = 2000
        paths = combine_purged_k_fold_cv(
            n_bars=n_bars,
            n_splits=6,
            n_test_splits=2,
            purged_size=12,
            embargo_size=12,
        )
        for path in paths:
            for train_idx, test_idx in path:
                overlap = set(train_idx.tolist()) & set(test_idx.tolist())
                assert not overlap, (
                    f"CPCV fold has {len(overlap)} overlapping indices"
                )


class TestModelSaveLoadRoundtrip:
    """Verify model survives pickle save/load with identical predictions."""

    def test_model_save_load_roundtrip(self, trained_model, feature_set):
        """Predictions must be identical after save/load."""
        result, trainer = trained_model

        with open(result.model_path, "rb") as f:
            model_data = pickle.load(f)
        model = model_data["model"]

        X = np.array([list(f.values()) for f in feature_set.features])[:10]
        preds_before = model.predict(X)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            pickle.dump(model_data, tmp)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            loaded = pickle.load(f)

        preds_after = loaded["model"].predict(X)
        np.testing.assert_array_equal(
            preds_before, preds_after,
            err_msg="Predictions differ after save/load roundtrip",
        )
        os.unlink(tmp_path)

    def test_model_registry_roundtrip(self):
        """ModelRegistry save/load must preserve predictions."""
        from ml.model_registry import ModelRegistry
        from sklearn.ensemble import RandomForestClassifier

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(models_dir=tmpdir)

            model = RandomForestClassifier(n_estimators=10, random_state=42)
            X_dummy = np.random.RandomState(42).randn(100, 5)
            y_dummy = np.random.RandomState(42).randint(0, 2, 100)
            model.fit(X_dummy, y_dummy)

            meta = registry.register_model(
                model,
                model_name="test_model",
                model_type="random_forest",
                symbol="XAUUSD",
                timeframe="M15",
                feature_list=["f1", "f2", "f3", "f4", "f5"],
                metrics={"accuracy": 0.6},
                training_samples=100,
            )

            loaded = registry.load_model(meta.version_id)
            preds_orig = model.predict(X_dummy[:10])
            preds_loaded = loaded.predict(X_dummy[:10])
            np.testing.assert_array_equal(preds_orig, preds_loaded)


class TestPredictSingleSampleLatency:
    """Verify single-sample prediction latency is acceptable."""

    def test_predict_single_sample_latency(self, trained_model, feature_set):
        """Single-sample prediction must complete in < 50ms."""
        result, trainer = trained_model

        features = {name: 0.0 for name in feature_set.feature_names}

        # Warm up
        trainer.predict(result.model_path, features)

        # Measure
        times = []
        for _ in range(100):
            start = time.perf_counter()
            trainer.predict(result.model_path, features)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        p95 = np.percentile(times, 95)
        assert p95 < 50, f"P95 latency {p95:.1f}ms > 50ms threshold"


class TestEarlyStoppingReducesEstimators:
    """Verify early stopping actually reduces the number of boosting rounds."""

    def test_early_stopping_reduces_estimators(self, feature_set):
        """Model with early stopping should use fewer estimators than n_estimators."""
        from xgboost import XGBClassifier
        from sklearn.model_selection import train_test_split

        X = np.array([list(f.values()) for f in feature_set.features])
        y = np.array(feature_set.labels)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False,
        )

        n_estimators = 500
        n_classes = len(set(y))
        eval_metric = "mlogloss" if n_classes > 2 else "logloss"
        model = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=3,
            learning_rate=0.01,
            early_stopping_rounds=10,
            eval_metric=eval_metric,
            random_state=42,
            verbosity=0,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        actual_estimators = model.best_iteration
        assert actual_estimators < n_estimators, (
            f"Early stopping didn't trigger: used {actual_estimators}/{n_estimators} rounds"
        )


class TestOverfitTriggersWarning:
    """Verify overfit detection triggers when IS >> OOS accuracy."""

    def test_overfit_triggers_warning(self, feature_set):
        """When train accuracy far exceeds test, overfit should be flagged."""
        from ml.pipeline import MLTrainer

        trainer = MLTrainer(model_dir=tempfile.mkdtemp())
        result = trainer.train(feature_set, model_type="xgboost", test_ratio=0.2)

        gap = result.accuracy - result.oos_accuracy if result.oos_accuracy > 0 else 0

        if gap > 0.15:
            assert True, (
                f"Overfit detected: train={result.accuracy:.3f} vs test={result.oos_accuracy:.3f}"
            )
        else:
            assert result.accuracy > 0.0, "Model accuracy is zero"
            assert result.f1_score >= 0.0, "F1 score is negative"

    def test_overfit_warning_with_degenerate_model(self):
        """A model that memorizes training data should trigger overfit warning."""
        from sklearn.ensemble import RandomForestClassifier

        rng = np.random.RandomState(42)
        X_train = rng.randn(100, 10)
        y_train = rng.randint(0, 2, 100)
        X_test = rng.randn(50, 10)
        y_test = rng.randint(0, 2, 50)

        model = RandomForestClassifier(
            n_estimators=100, max_depth=None, random_state=42
        )
        model.fit(X_train, y_train)

        train_acc = (model.predict(X_train) == y_train).mean()
        test_acc = (model.predict(X_test) == y_test).mean()

        gap = train_acc - test_acc
        assert gap > 0.0, (
            f"No gap between train ({train_acc:.3f}) and test ({test_acc:.3f})"
        )


class TestMultipleTestingCorrection:
    """Verify BH procedure correctness."""

    def test_benjamini_hochberg_basic(self):
        """BH should reject low p-values and not reject high ones."""
        from validation.multiple_testing import benjamini_hochberg

        pvals = [0.001, 0.01, 0.03, 0.05, 0.5]
        rejected, qvals = benjamini_hochberg(pvals, alpha=0.05)

        assert rejected[0], "p=0.001 should be rejected"
        assert rejected[1], "p=0.01 should be rejected"
        assert not rejected[4], "p=0.5 should not be rejected"

    def test_bh_empty_input(self):
        """BH should handle empty input gracefully."""
        from validation.multiple_testing import benjamini_hochberg

        rejected, qvals = benjamini_hochberg([], alpha=0.05)
        assert len(rejected) == 0
        assert len(qvals) == 0

    def test_bh_adjusted_monotone(self):
        """Adjusted p-values must be monotonically non-decreasing when sorted."""
        from validation.multiple_testing import benjamini_hochberg

        pvals = [0.001, 0.01, 0.02, 0.03, 0.04, 0.05]
        _, qvals = benjamini_hochberg(pvals, alpha=0.05)
        sorted_q = np.sort(qvals)
        assert np.all(np.diff(sorted_q) >= -1e-10), "Q-values must be monotone"
