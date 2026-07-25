"""
Tests for auto_retrain — evaluate_model and hot_swap logic.

Covers:
  - evaluate_model guard clauses (empty, None, no features → NaN)
  - evaluate_model discriminates real model quality (informative vs. noise
    labels), using the real implementation end-to-end (only the warehouse
    data-loading I/O boundary is faked — everything downstream of
    label_from_source() runs for real: feature engineering, the
    purge/embargo-derived OOS split, model.predict(), the P&L simulation,
    and validation.deflated_sharpe.deflated_sharpe_ratio()).
  - hot_swap: first model must clear a real bar (not save unconditionally),
    a genuinely-better challenger promotes, a genuinely-worse one doesn't —
    all using the real evaluate_model(), not a mock.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

# ---------------------------------------------------------------------------
# Import auto_retrain as a standalone module (scripts/ has no __init__.py)
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("auto_retrain", _SCRIPT_DIR / "auto_retrain.py")
assert _SPEC is not None and _SPEC.loader is not None
_auto_retrain = importlib.util.module_from_spec(_SPEC)
sys.modules["auto_retrain"] = _auto_retrain
_SPEC.loader.exec_module(_auto_retrain)

evaluate_model = _auto_retrain.evaluate_model
hot_swap = _auto_retrain.hot_swap

sys.path.insert(0, str(_SCRIPT_DIR.parent))
from ml.pipeline import FeatureEngineer  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nan_metrics():
    """Return a ModelMetrics-like object with NaN values."""
    from dataclasses import dataclass

    @dataclass
    class ModelMetrics:
        deflated_sharpe: float
        oos_max_drawdown: float

    return ModelMetrics(deflated_sharpe=float("nan"), oos_max_drawdown=float("nan"))


def _make_model_data(model=None, feature_names=None):
    """Build a minimal model_data dict."""
    return {
        "model": model,
        "feature_names": feature_names or [],
    }


def _synthetic_ohlcv(n: int = 2200, seed: int = 0) -> pd.DataFrame:
    """A deterministic, cyclical synthetic price series.

    The regular sine-wave structure gives technical indicators (RSI, EMA
    cross, MACD, Bollinger position, …) a genuine, learnable relationship
    to the future triple-barrier outcome — this is what lets a model
    trained on the TRUE labels actually beat a model trained on shuffled
    (noise) labels once both are evaluated against the true held-out
    labels inside evaluate_model().
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    base = 100 + 8 * np.sin(t / 15.0) + 3 * np.sin(t / 55.0)
    close = base + rng.normal(0, 0.05, n)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + rng.uniform(0.01, 0.15, n)
    low = np.minimum(open_, close) - rng.uniform(0.01, 0.15, n)
    volume = rng.uniform(100, 1000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def _train_on(df: pd.DataFrame, *, shuffle_labels: bool, seed: int) -> dict:
    """Train a real RandomForestClassifier on df's triple-barrier labels.

    shuffle_labels=True breaks any real feature/label relationship (pure
    noise) — the model this produces cannot know anything true about the
    real held-out labels evaluate_model() will later check it against.

    Trains ONLY on the portion of the data evaluate_model() will NOT use as
    its own OOS fold -- the identical purge_embargo_split_indices() call
    evaluate_model() itself uses (test_ratio=0.2, gap=12), not a re-derived
    split. This matters: fitting on the full dataset (or a different split)
    would let the model see (and a tree ensemble can partially memorize)
    rows it's later "evaluated" against, which would make even the
    noise-label model look artificially good -- not a real out-of-sample
    test at all.
    """
    from ml.pipeline import purge_embargo_split_indices

    feature_set = FeatureEngineer().generate_features(df)
    split, _ = purge_embargo_split_indices(len(feature_set.features), test_ratio=0.2, gap=12)
    train_features = feature_set.features[:split]
    train_labels = feature_set.labels[:split]

    x = np.array([list(f.values()) for f in train_features])
    y = np.array(train_labels)
    if shuffle_labels:
        y = np.random.default_rng(seed).permutation(y)
    model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=seed)
    model.fit(x, y)
    return {
        "model": model,
        "feature_names": feature_set.feature_names,
        "model_type": "random_forest",
        "version": "test",
    }


# ---------------------------------------------------------------------------
# evaluate_model guard clauses
# ---------------------------------------------------------------------------


class TestEvaluateModelGuards:
    """evaluate_model returns NaN metrics for invalid inputs."""

    def test_evaluate_model_empty_returns_nan(self):
        """Empty dict → NaN metrics."""
        result = evaluate_model({})
        assert math.isnan(result.deflated_sharpe)
        assert math.isnan(result.oos_max_drawdown)

    def test_evaluate_model_none_returns_nan(self):
        """None input → NaN metrics."""
        result = evaluate_model(None)
        assert math.isnan(result.deflated_sharpe)
        assert math.isnan(result.oos_max_drawdown)

    def test_evaluate_model_no_features_returns_nan(self):
        """Model without feature_names → NaN metrics."""
        mock_model = MagicMock()
        data = _make_model_data(model=mock_model, feature_names=[])
        result = evaluate_model(data)
        assert math.isnan(result.deflated_sharpe)
        assert math.isnan(result.oos_max_drawdown)


# ---------------------------------------------------------------------------
# hot_swap
# ---------------------------------------------------------------------------


class TestHotSwap:
    """hot_swap champion/challenger replacement logic."""

    def test_hot_swap_no_champion_rejects_failed_evaluation(self, tmp_path):
        """First model (no champion) with a failed/NaN evaluation must NOT
        be promoted unconditionally -- this was the exact bug: zero
        evaluation just because there's nothing to compare against yet."""
        champion_path = tmp_path / "champion.pkl"

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=None),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            challenger_metrics = _nan_metrics()

            result = hot_swap(challenger_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()

    def test_hot_swap_no_champion_saves_when_bar_cleared(self, tmp_path):
        """First model (no champion), real positive deflated Sharpe -> saved."""
        champion_path = tmp_path / "champion.pkl"

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=None),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            challenger_metrics = _nan_metrics()
            challenger_metrics.deflated_sharpe = 0.10  # > _FIRST_CHAMPION_MIN_SHARPE (0.0)
            challenger_metrics.oos_max_drawdown = 3.0

            result = hot_swap(challenger_data, challenger_metrics)

        assert result is True
        mock_save.assert_called_once_with(challenger_data)

    def test_hot_swap_better_replaces(self, tmp_path):
        """Challenger DSR > champion DSR * 1.05 AND DD < champion DD → swap."""
        champion_path = tmp_path / "champion.pkl"
        champion_data = _make_model_data(model=MagicMock(), feature_names=["f1"])

        champion_metrics = _nan_metrics()
        champion_metrics.deflated_sharpe = 0.60
        champion_metrics.oos_max_drawdown = 10.0

        # Challenger beats both thresholds
        challenger_metrics = _nan_metrics()
        challenger_metrics.deflated_sharpe = 0.70  # > 0.60 * 1.05 = 0.63
        challenger_metrics.oos_max_drawdown = 5.0  # < 10.0

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=champion_data),
            patch.object(_auto_retrain, "evaluate_model", return_value=champion_metrics),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            result = hot_swap(challenger_data, challenger_metrics)

        assert result is True
        mock_save.assert_called_once_with(challenger_data)

    def test_hot_swap_worse_keeps(self, tmp_path):
        """Challenger not better → no swap, return False."""
        champion_path = tmp_path / "champion.pkl"
        champion_data = _make_model_data(model=MagicMock(), feature_names=["f1"])

        champion_metrics = _nan_metrics()
        champion_metrics.deflated_sharpe = 0.80
        champion_metrics.oos_max_drawdown = 5.0

        # Challenger DSR too low (0.82 < 0.80 * 1.05 = 0.84)
        challenger_metrics = _nan_metrics()
        challenger_metrics.deflated_sharpe = 0.82
        challenger_metrics.oos_max_drawdown = 4.0

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=champion_data),
            patch.object(_auto_retrain, "evaluate_model", return_value=champion_metrics),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            result = hot_swap(challenger_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# evaluate_model — real computation (behavioral, not just structural)
# ---------------------------------------------------------------------------


def _synthetic_labeled_df(n=900, seed=7):
    """Synthetic random-walk OHLCV, triple-barrier labeled -- enough bars to
    clear MIN_SAMPLES and FeatureEngineer's 300-bar indicator warmup."""
    import numpy as np
    import pandas as pd

    from ml.labeling import prepare_labeled_dataset

    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 1.0, n)
    close = 100 + np.cumsum(steps)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.uniform(100, 1000, n)
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="h"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "symbol": "XAUUSD",
        }
    )
    return prepare_labeled_dataset(df)


class TestEvaluateModelRealComputation:
    """evaluate_model must compute real OOS Sharpe/drawdown from actual model
    predictions and actual triple-barrier outcomes -- not a hardcoded constant.
    This is the behavioral check for the bug this file exists to catch: a
    placeholder that produces a label that looks like evidence but isn't."""

    def test_evaluate_model_uses_real_data_not_dummy_constants(self):
        """An always-predict-win model must NOT get the old hardcoded
        deflated_sharpe=1.0 / oos_max_drawdown=10.0 -- it must reflect the
        actual (synthetic, random-walk) outcomes."""
        import numpy as np

        labeled = _synthetic_labeled_df()

        class AlwaysWinModel:
            def predict(self, x):
                return np.ones(len(x), dtype=int)

        with patch.object(_auto_retrain, "label_from_source", return_value=labeled):
            feature_names = _auto_retrain.FeatureEngineer().generate_features(labeled).feature_names
            model_data = {"model": AlwaysWinModel(), "feature_names": feature_names}
            result = evaluate_model(model_data)

        assert not math.isnan(result.deflated_sharpe)
        assert not math.isnan(result.oos_max_drawdown)
        # Old bug returned exactly these two constants regardless of input.
        assert result.deflated_sharpe != 1.0
        assert result.oos_max_drawdown != 10.0
        assert result.n_trades >= _auto_retrain._MIN_EVAL_TRADES

    def test_evaluate_model_fails_closed_on_vocabulary_drift(self):
        """Model trained on a feature the live pipeline no longer produces ->
        NaN, not a score computed from misaligned columns (same discipline as
        the 2B.2 live-inference vocabulary-drift gate)."""
        import numpy as np

        labeled = _synthetic_labeled_df()

        class DummyModel:
            def predict(self, x):
                return np.ones(len(x), dtype=int)

        with patch.object(_auto_retrain, "label_from_source", return_value=labeled):
            model_data = {"model": DummyModel(), "feature_names": ["this_feature_does_not_exist"]}
            result = evaluate_model(model_data)

        assert math.isnan(result.deflated_sharpe)
        assert math.isnan(result.oos_max_drawdown)


# ---------------------------------------------------------------------------
# Real quality discrimination -- no mocked evaluate_model() anywhere below.
# Only the warehouse data-loading I/O boundary (label_from_source) is faked;
# feature engineering, the OOS split, model.predict(), the P&L simulation,
# and deflated_sharpe_ratio() all run for real, on two genuinely different
# real models (RandomForestClassifier fit on true triple-barrier labels vs.
# the same features fit on shuffled/noise labels).
# ---------------------------------------------------------------------------


class TestEvaluateModelDiscriminatesRealQuality:
    def test_informative_model_beats_noise_model(self):
        """A model trained on the true (learnable) labels must score a
        genuinely higher deflated Sharpe than a model trained on shuffled
        (noise) labels, once both are evaluated against the SAME true
        held-out labels. This is the actual proof the gate isn't hardcoded:
        it requires evaluate_model() to run predict() and score real,
        different P&L for two models that really do differ in quality."""
        df = _synthetic_ohlcv()
        good_data = _train_on(df, shuffle_labels=False, seed=1)
        noise_data = _train_on(df, shuffle_labels=True, seed=2)

        with patch.object(_auto_retrain, "label_from_source", return_value=df):
            good_metrics = evaluate_model(good_data)
            noise_metrics = evaluate_model(noise_data)

        assert not math.isnan(good_metrics.deflated_sharpe)
        assert not math.isnan(noise_metrics.deflated_sharpe)
        assert good_metrics.deflated_sharpe > noise_metrics.deflated_sharpe
        assert good_metrics.deflated_sharpe != noise_metrics.deflated_sharpe


class TestHotSwapRealEndToEnd:
    """hot_swap() using the REAL evaluate_model() throughout -- no
    `patch.object(_auto_retrain, "evaluate_model", ...)` anywhere here."""

    def test_real_better_challenger_promotes(self, tmp_path):
        df = _synthetic_ohlcv()
        good_data = _train_on(df, shuffle_labels=False, seed=1)
        noise_data = _train_on(df, shuffle_labels=True, seed=2)

        with (
            patch.object(_auto_retrain, "label_from_source", return_value=df),
            patch.object(_auto_retrain, "CHAMPION_PATH", tmp_path / "champion.pkl"),
            patch.object(_auto_retrain, "load_champion", return_value=noise_data),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_metrics = evaluate_model(good_data)  # real call, not mocked
            result = hot_swap(good_data, challenger_metrics)

        assert result is True
        mock_save.assert_called_once_with(good_data)

    def test_real_worse_challenger_rejected(self, tmp_path):
        df = _synthetic_ohlcv()
        good_data = _train_on(df, shuffle_labels=False, seed=1)
        noise_data = _train_on(df, shuffle_labels=True, seed=2)

        with (
            patch.object(_auto_retrain, "label_from_source", return_value=df),
            patch.object(_auto_retrain, "CHAMPION_PATH", tmp_path / "champion.pkl"),
            patch.object(_auto_retrain, "load_champion", return_value=good_data),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_metrics = evaluate_model(noise_data)  # real call, not mocked
            result = hot_swap(noise_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()

    def test_real_first_champion_rejects_noise_model(self, tmp_path):
        """No existing champion + a real (noise-trained, no genuine edge)
        model -> must still be rejected by a real evaluation, not
        auto-promoted just because nothing exists to compare against."""
        df = _synthetic_ohlcv()
        noise_data = _train_on(df, shuffle_labels=True, seed=2)

        with (
            patch.object(_auto_retrain, "label_from_source", return_value=df),
            patch.object(_auto_retrain, "CHAMPION_PATH", tmp_path / "champion.pkl"),
            patch.object(_auto_retrain, "load_champion", return_value=None),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_metrics = evaluate_model(noise_data)  # real call, not mocked
            result = hot_swap(noise_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# hot_swap — negative-Sharpe reality (this project has no confirmed edge yet;
# see reports/go_live_gate_corrected_sequencing.md)
# ---------------------------------------------------------------------------


class TestHotSwapNegativeSharpeReality:
    """A `champion * 1.05` threshold silently loosens once champion is
    negative (multiplying a negative number by 1.05 makes it MORE negative,
    i.e. easier to clear). These tests pin the additive-margin fix
    (MIN_SHARPE_IMPROVEMENT) that replaced it."""

    def test_slightly_less_bad_challenger_does_not_promote(self, tmp_path):
        champion_path = tmp_path / "champion.pkl"
        champion_data = _make_model_data(model=MagicMock(), feature_names=["f1"])

        champion_metrics = _nan_metrics()
        champion_metrics.deflated_sharpe = -0.50
        champion_metrics.oos_max_drawdown = 8.0

        # Only marginally less negative -- must not clear the real gate.
        challenger_metrics = _nan_metrics()
        challenger_metrics.deflated_sharpe = -0.48
        challenger_metrics.oos_max_drawdown = 7.0

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=champion_data),
            patch.object(_auto_retrain, "evaluate_model", return_value=champion_metrics),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            result = hot_swap(challenger_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()

    def test_genuinely_less_bad_challenger_promotes(self, tmp_path):
        champion_path = tmp_path / "champion.pkl"
        champion_data = _make_model_data(model=MagicMock(), feature_names=["f1"])

        champion_metrics = _nan_metrics()
        champion_metrics.deflated_sharpe = -0.50
        champion_metrics.oos_max_drawdown = 8.0

        challenger_metrics = _nan_metrics()
        challenger_metrics.deflated_sharpe = -0.30  # clears the 0.05 margin
        challenger_metrics.oos_max_drawdown = 7.0

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=champion_data),
            patch.object(_auto_retrain, "evaluate_model", return_value=champion_metrics),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            result = hot_swap(challenger_data, challenger_metrics)

        assert result is True
        mock_save.assert_called_once_with(challenger_data)

    def test_nan_metrics_never_promote(self, tmp_path):
        """Evaluation failure (NaN) on either side must fail closed, not
        silently bypass the comparison via Python's NaN-is-never-True
        semantics (`NaN <= x` is always False)."""
        champion_path = tmp_path / "champion.pkl"
        champion_data = _make_model_data(model=MagicMock(), feature_names=["f1"])

        champion_metrics = _nan_metrics()
        champion_metrics.deflated_sharpe = -0.50
        champion_metrics.oos_max_drawdown = 8.0

        challenger_metrics = _nan_metrics()  # NaN/NaN -- evaluation failed

        with (
            patch.object(_auto_retrain, "CHAMPION_PATH", champion_path),
            patch.object(_auto_retrain, "load_champion", return_value=champion_data),
            patch.object(_auto_retrain, "evaluate_model", return_value=champion_metrics),
            patch.object(_auto_retrain, "save_champion") as mock_save,
        ):
            challenger_data = _make_model_data(model=MagicMock(), feature_names=["f1"])
            result = hot_swap(challenger_data, challenger_metrics)

        assert result is False
        mock_save.assert_not_called()
