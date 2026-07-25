"""Tests for ml.ensemble's label-binarization + row-wise predict adapter.

Context: TripleBoostEnsemble.fit() fits XGBClassifier/LGBMClassifier/
CatBoostClassifier directly on whatever y is passed. XGBoost requires
contiguous {0..K-1} class labels, but ml.labeling.compute_triple_barrier()
produces {-1 (loss), 0 (timeout), 1 (win)}, which XGBoost rejects.
binarize_triple_barrier_labels() collapses that to {0, 1} (win -> 1,
everything else -> 0) without touching compute_triple_barrier() or
TripleBoostEnsemble's binary-oriented predict() logic.

Separately, TripleBoostEnsemble.predict(X) returns one aggregated
EnsemblePrediction for a whole batch (its existing callers in
tests/test_new_modules_integration.py and tests/test_new_modules_benchmark.py
rely on that shape). scripts/auto_retrain.py::evaluate_model() needs a
per-row 0/1 array instead -- RowwisePredictAdapter provides that without
changing TripleBoostEnsemble.predict() itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
if str(_QUANT_OS_ROOT) not in sys.path:
    sys.path.insert(0, str(_QUANT_OS_ROOT))

from ml.ensemble import (  # noqa: E402
    RowwisePredictAdapter,
    TripleBoostEnsemble,
    binarize_triple_barrier_labels,
)


class TestBinarizeTripleBarrierLabels:
    def test_win_maps_to_one(self):
        out = binarize_triple_barrier_labels([1, 1, 1])
        assert list(out) == [1, 1, 1]

    def test_loss_and_timeout_map_to_zero(self):
        out = binarize_triple_barrier_labels([-1, 0, -1, 0])
        assert list(out) == [0, 0, 0, 0]

    def test_mixed_labels(self):
        out = binarize_triple_barrier_labels([1, -1, 0, 1, -1])
        assert list(out) == [1, 0, 0, 1, 0]

    def test_accepts_numpy_array_and_returns_int_dtype(self):
        out = binarize_triple_barrier_labels(np.array([1, -1, 0]))
        assert out.dtype.kind in ("i", "u")
        assert set(np.unique(out)).issubset({0, 1})

    def test_output_is_valid_xgboost_label_set(self):
        """Contiguous {0, 1} -- exactly what XGBClassifier requires and
        what the raw {-1, 0, 1} triple-barrier labels are NOT."""
        raw = [-1, 0, 1, -1, 0, 1, 1, 1, -1, 0]
        out = binarize_triple_barrier_labels(raw)
        assert set(np.unique(out)) == {0, 1}


class TestRowwisePredictAdapter:
    """Uses a real (small, fast) TripleBoostEnsemble, fit via its normal
    fit() path on already-binarized labels -- matching how the retrain
    script uses it."""

    @pytest.fixture()
    def fitted_ensemble(self):
        rng = np.random.default_rng(42)
        X = rng.normal(size=(150, 4))
        y_raw = np.where(X[:, 0] + X[:, 1] > 0, 1, rng.choice([-1, 0], size=150))
        y_bin = binarize_triple_barrier_labels(y_raw)

        # Fit small/fast versions directly (mirrors existing benchmark/
        # integration tests' pattern of overriding .models for speed).
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from xgboost import XGBClassifier

        ensemble = TripleBoostEnsemble()
        ensemble.models = {
            "lgbm": LGBMClassifier(n_estimators=10, max_depth=3, verbose=-1),
            "catboost": CatBoostClassifier(iterations=10, depth=3, verbose=0),
            "xgboost": XGBClassifier(n_estimators=10, max_depth=3),
        }
        ensemble._fitted = True
        for model in ensemble.models.values():
            model.fit(X[:120], y_bin[:120])
        return ensemble, X[120:]

    def test_predict_returns_per_row_array_not_single_object(self, fitted_ensemble):
        ensemble, X_test = fitted_ensemble
        adapter = RowwisePredictAdapter(ensemble)

        predictions = adapter.predict(X_test)

        assert isinstance(predictions, np.ndarray)
        assert predictions.shape == (len(X_test),)
        assert set(np.unique(predictions)).issubset({0, 1})

    def test_predict_matches_predict_proba_threshold(self, fitted_ensemble):
        ensemble, X_test = fitted_ensemble
        adapter = RowwisePredictAdapter(ensemble)

        predictions = adapter.predict(X_test)
        proba = adapter.predict_proba(X_test)

        expected = (proba[:, 1] > 0.5).astype(int)
        np.testing.assert_array_equal(predictions, expected)

    def test_underlying_ensemble_predict_is_unchanged(self, fitted_ensemble):
        """The adapter must not mutate/break TripleBoostEnsemble's own
        aggregate .predict() -- its existing callers rely on that shape."""
        from ml.ensemble import EnsemblePrediction

        ensemble, X_test = fitted_ensemble
        RowwisePredictAdapter(ensemble)  # constructing the adapter is a no-op on the ensemble

        result = ensemble.predict(X_test)
        assert isinstance(result, EnsemblePrediction)
        assert isinstance(result.prediction, int)


class TestRealFitEndToEnd:
    """Exercises the actual blocker end-to-end through TripleBoostEnsemble's
    real .fit() (not the hand-set-.models/.​_fitted bypass the other fixtures
    use) -- this is what a bare retrain call site would hit.

    Confirms both halves of the fix:
      1. The crash is real: .fit() on raw {-1, 0, 1} triple-barrier labels
         raises (XGBoost rejects non-contiguous class labels).
      2. The fix works: .fit() on binarize_triple_barrier_labels(raw) labels
         succeeds, and RowwisePredictAdapter(...).predict() round-trips to a
         per-row array in the binarized {0, 1} label space (not an internal
         {0, 1, 2}-style artifact) -- the space evaluate_model() expects,
         where 1 always means "predicted win".
    """

    @staticmethod
    def _raw_labels_and_features(n=150, seed=3):
        rng = np.random.default_rng(seed)
        X = rng.normal(size=(n, 4))
        # Real triple-barrier-shaped labels: {-1, 0, 1}, not contiguous from 0.
        y_raw = np.where(
            X[:, 0] + X[:, 1] > 0.3,
            1,
            np.where(X[:, 0] + X[:, 1] < -0.3, -1, 0),
        )
        return X, y_raw

    def test_fit_on_raw_triple_barrier_labels_raises(self):
        """Pins the actual blocker: real .fit() on unbinarized {-1, 0, 1}
        labels must raise -- this is the bug Task 2 exists to fix."""
        X, y_raw = self._raw_labels_and_features()
        assert set(np.unique(y_raw)) == {-1, 0, 1}

        ensemble = TripleBoostEnsemble()
        with pytest.raises(Exception):  # noqa: B017 — xgboost raises ValueError; exact type is xgboost-internal
            ensemble.fit(X[:120], y_raw[:120])

    def test_real_fit_on_binarized_labels_succeeds_and_adapter_round_trips(self):
        """Real .fit() (not a bypassed fixture) on binarized labels succeeds,
        and RowwisePredictAdapter gives back a per-row array in the {0, 1}
        space the fit used -- not {0, 1, 2} or any other internal encoding."""
        X, y_raw = self._raw_labels_and_features()
        y_bin = binarize_triple_barrier_labels(y_raw)
        assert set(np.unique(y_bin)) == {0, 1}

        ensemble = TripleBoostEnsemble()
        ensemble.fit(X[:120], y_bin[:120])  # real fit(), no bypass
        assert ensemble._fitted is True

        adapter = RowwisePredictAdapter(ensemble)
        predictions = adapter.predict(X[120:])

        assert isinstance(predictions, np.ndarray)
        assert predictions.shape == (len(X[120:]),)
        assert set(np.unique(predictions)).issubset({0, 1})
