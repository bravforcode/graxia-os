"""
Triple Boost Ensemble — LightGBM + CatBoost + XGBoost weighted ensemble.

Expected improvement: +15-25% Sharpe over single model.

ponytail: Simple weighted average ensemble. Upgrade path: stacking meta-learner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class EnsemblePrediction:
    """Result from ensemble prediction."""

    prediction: int
    confidence: float
    model_predictions: dict[str, float]
    ensemble_weights: dict[str, float]


class TripleBoostEnsemble:
    """Weighted ensemble of LightGBM, CatBoost, and XGBoost.

    Each model votes with its predicted probability. The ensemble
    combines predictions using configurable weights.

    Example:
        ensemble = TripleBoostEnsemble()
        ensemble.fit(X_train, y_train)
        result = ensemble.predict(X_test)
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {"lgbm": 0.4, "catboost": 0.35, "xgboost": 0.25}
        self.models: dict[str, Any] = {}
        self._fitted = False

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        eval_set: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> None:
        """Fit all three models.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target labels
            eval_set: Optional (X_val, y_val) for early stopping
        """
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from xgboost import XGBClassifier

        self.models = {
            "lgbm": LGBMClassifier(
                n_estimators=500,
                learning_rate=0.05,
                max_depth=6,
                num_leaves=31,
                min_child_samples=20,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                random_state=42,
                verbose=-1,
            ),
            "catboost": CatBoostClassifier(
                iterations=500,
                learning_rate=0.05,
                depth=6,
                l2_leaf_reg=3,
                random_seed=42,
                verbose=0,
            ),
            "xgboost": XGBClassifier(
                n_estimators=500,
                learning_rate=0.05,
                max_depth=6,
                min_child_weight=5,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                random_state=42,
            ),
        }

        for name, model in self.models.items():
            if eval_set is not None and name == "xgboost":
                model.fit(X, y, eval_set=[eval_set], verbose=False)
            elif name == "catboost":
                model.fit(X, y, eval_set=eval_set if eval_set else None, verbose=0)
            elif name == "lgbm":
                model.fit(X, y, eval_set=[eval_set] if eval_set else None)
            else:
                model.fit(X, y, eval_set=[eval_set] if eval_set else None)

        self._fitted = True

    def predict(self, X: np.ndarray) -> EnsemblePrediction:
        """Predict using weighted ensemble.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            EnsemblePrediction with aggregated prediction
        """
        if not self._fitted:
            raise RuntimeError("Ensemble not fitted. Call fit() first.")

        predictions = {}
        for name, model in self.models.items():
            proba = model.predict_proba(X)
            if proba.ndim == 2 and proba.shape[1] == 2:
                predictions[name] = proba[:, 1]
            elif proba.ndim == 1:
                predictions[name] = proba
            else:
                predictions[name] = proba[:, -1]  # last column for multiclass

        # Weighted average
        ensemble_pred = sum(predictions[name] * self.weights[name] for name in self.models)

        # For batch: return mean prediction
        mean_pred = float(np.mean(ensemble_pred))
        prediction = int(mean_pred > 0.5)
        confidence = float(np.mean(np.maximum(ensemble_pred, 1 - ensemble_pred)))

        return EnsemblePrediction(
            prediction=prediction,
            confidence=confidence,
            model_predictions={name: float(np.mean(pred)) for name, pred in predictions.items()},
            ensemble_weights=self.weights,
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return ensemble probabilities (for compatibility with sklearn API).

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Array of shape (n_samples, 2) with [prob_class_0, prob_class_1]
        """
        if not self._fitted:
            raise RuntimeError("Ensemble not fitted. Call fit() first.")

        predictions = {}
        for name, model in self.models.items():
            proba = model.predict_proba(X)
            if proba.ndim == 2 and proba.shape[1] == 2:
                predictions[name] = proba[:, 1]
            elif proba.ndim == 1:
                predictions[name] = proba
            else:
                predictions[name] = proba[:, -1]  # last column for multiclass

        ensemble_pred = sum(predictions[name] * self.weights[name] for name in self.models)
        return np.column_stack([1 - ensemble_pred, ensemble_pred])

    def get_feature_importance(self) -> dict[str, dict[str, float]]:
        """Get feature importance from each model.

        Returns:
            Dict mapping model_name -> {feature_name: importance}
        """
        if not self._fitted:
            return {}

        importance = {}
        for name, model in self.models.items():
            if hasattr(model, "feature_importances_"):
                importance[name] = {str(i): float(v) for i, v in enumerate(model.feature_importances_)}
        return importance


def binarize_triple_barrier_labels(labels: Any) -> np.ndarray:
    """Map triple-barrier {-1 (loss), 0 (timeout), 1 (win)} labels to binary
    {0, 1} for TripleBoostEnsemble's underlying classifiers.

    XGBoost/LightGBM/CatBoostClassifier all require contiguous {0..K-1}
    class labels; ml.labeling.compute_triple_barrier() produces {-1, 0, 1},
    which XGBoost rejects outright. Rather than changing
    compute_triple_barrier() (used elsewhere for the real 3-class case) or
    TripleBoostEnsemble's binary-oriented internals (``prediction =
    int(mean_pred > 0.5)``), collapse the label at the boundary instead:
    win (1) -> 1, everything else (loss=-1, timeout=0) -> 0 ("not a win").

    This matches how scripts/auto_retrain.py::evaluate_model() already
    consumes predictions from a model's ``.predict()`` (``if pred != 1:
    continue`` -- a trade is only taken when the model predicts class 1,
    i.e. "win").
    """
    arr = np.asarray(labels)
    return (arr == 1).astype(int)


class RowwisePredictAdapter:
    """Adapter exposing a per-row ``.predict(X) -> ndarray[int]`` for a
    fitted TripleBoostEnsemble.

    TripleBoostEnsemble.predict(X) returns a single aggregated
    EnsemblePrediction for the whole batch (designed for one real-time
    inference call -- see its docstring and existing callers in
    tests/test_new_modules_integration.py / tests/test_new_modules_benchmark.py,
    which rely on that shape and are NOT touched by this adapter).
    Batch-scoring consumers (e.g. scripts/auto_retrain.py::evaluate_model(),
    which does ``predictions = model.predict(x_oos)`` then zips over
    per-row predicted vs. actual) need one prediction per row instead.

    TripleBoostEnsemble.predict_proba(X) is already row-wise
    ((n_samples, 2)); this just applies the same 0.5 threshold
    TripleBoostEnsemble.predict() uses on its batch mean, per row.
    """

    def __init__(self, ensemble: TripleBoostEnsemble):
        self._ensemble = ensemble

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self._ensemble.predict_proba(X)
        return (proba[:, 1] > 0.5).astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._ensemble.predict_proba(X)
