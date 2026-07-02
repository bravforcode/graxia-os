"""Phase 5 — Train Per-Asset Dual-Head Models (Direction + Magnitude).

Trains two XGBoost models per symbol:
  1. Direction head — classifier for next-bar direction (up/down)
  2. Magnitude head — regressor for next-bar return magnitude

Data split: 70% train / 15% val / 15% test (time-based, no shuffle).
Cross-validation: purged k-fold (5 folds, embargo=5 bars).

Usage:
    python scripts/train_dual_head.py --symbol XAUUSD
    python scripts/train_dual_head.py --symbol ALL   # train all 4 targets
    python scripts/train_dual_head.py --symbol XAUUSD --skip-features  # skip if parquets exist
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

warnings.filterwarnings("ignore")

# ── Path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
FEATURES_DIR = PROJECT_ROOT / "artifacts" / "features_v3"
MODELS_DIR = PROJECT_ROOT / "artifacts" / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"

FEATURES_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

TARGET_SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]

# ── Feature building (from Phase 3) ────────────────────────────────────────


def build_features_if_needed(symbol: str, timeframe: str = "M15") -> Path:
    """Return path to feature parquet, building it if it doesn't exist."""
    parquet_path = FEATURES_DIR / f"features_v3_{symbol}_{timeframe}.parquet"
    if parquet_path.exists():
        logger.info("  Feature parquet exists: %s", parquet_path.name)
        return parquet_path

    logger.info("  Building features for %s from raw CSV...", symbol)
    # Import build_features from Phase 3 script
    from scripts.build_features_v3_multi_asset import build_features

    df = build_features(symbol, timeframe)
    df.to_parquet(parquet_path, index=False)
    logger.info("  Saved %d rows x %d cols -> %s", len(df), len(df.columns), parquet_path.name)
    return parquet_path


# ── Label creation ──────────────────────────────────────────────────────────


def create_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Add direction and magnitude labels.

    Direction: 1 if next bar's close > current close, else 0.
    Magnitude: signed return of next bar (close[t+1] - close[t]) / close[t].
    """
    df = df.copy()
    close = df["close"].to_numpy()

    # Next-bar return (signed)
    next_return = np.empty(len(close))
    next_return[:-1] = (close[1:] - close[:-1]) / close[:-1]
    next_return[-1] = np.nan

    df["target_direction"] = (next_return > 0).astype(float)
    df["target_magnitude"] = next_return

    # Drop last row (no label)
    df = df.dropna(subset=["target_direction", "target_magnitude"]).reset_index(drop=True)
    return df


# ── Feature column selection ────────────────────────────────────────────────

EXCLUDE_COLS = {
    "target",
    "target_return",
    "target_direction",
    "target_magnitude",
    "symbol",
    "time",
    "freq",
    "timestamp",
    "tb_label",
    "tb_bar_hit",
    "tb_side",
    "tb_ret",
    "tb_k_upper",
    "tb_k_lower",
    # Raw OHLCV — not predictive features (XGBoost tree splits on price level
    # are not generalizable; use derived SMC/macro features instead)
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Select numeric feature columns, excluding labels and metadata."""
    cols = []
    for c in df.columns:
        if c in EXCLUDE_COLS:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


# ── Purged k-fold CV ────────────────────────────────────────────────────────


def purged_kfold_cv(
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
    embargo: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate purged k-fold train/val splits for time-series.

    Purging: remove training samples whose labels overlap with validation.
    Embargo: gap between train and val sets.

    Returns list of (train_indices, val_indices).
    """
    n = len(X)
    fold_size = n // n_folds
    splits = []

    for k in range(n_folds):
        val_start = k * fold_size
        val_end = min((k + 1) * fold_size, n)

        # Embargo: gap before validation
        embargo_start = max(0, val_start - embargo)
        # Embargo: gap after validation
        embargo_end = min(n, val_end + embargo)

        # Train = everything except validation + embargo
        train_idx = np.concatenate(
            [
                np.arange(0, embargo_start),
                np.arange(embargo_end, n),
            ]
        )
        val_idx = np.arange(val_start, val_end)
        splits.append((train_idx, val_idx))

    return splits


# ── Training ────────────────────────────────────────────────────────────────


def train_direction_head(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
) -> xgb.XGBClassifier:
    """Train direction (classification) head with early stopping."""
    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="logloss",
        early_stopping_rounds=30,
        verbosity=0,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    logger.info("    Direction head: best_iteration=%d", model.best_iteration)
    return model


def train_magnitude_head(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
) -> xgb.XGBRegressor:
    """Train magnitude (regression) head with early stopping."""
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="rmse",
        early_stopping_rounds=30,
        verbosity=0,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    logger.info("    Magnitude head: best_iteration=%d", model.best_iteration)
    return model


# ── Metrics ─────────────────────────────────────────────────────────────────


def compute_direction_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Classification metrics for direction head."""
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "n_samples": int(len(y_true)),
        "n_up_true": int(y_true.sum()),
        "n_down_true": int(len(y_true) - y_true.sum()),
        "n_up_pred": int(y_pred.sum()),
        "n_down_pred": int(len(y_pred) - y_pred.sum()),
    }


def compute_magnitude_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Regression metrics for magnitude head."""
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {
        "rmse": round(rmse, 6),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 6),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "mape": round(float(np.mean(np.abs(y_true) / (np.abs(y_true) + 1e-10)) * 100), 4),
        "n_samples": int(len(y_true)),
        "mean_true": round(float(y_true.mean()), 6),
        "std_true": round(float(y_true.std()), 6),
        "mean_pred": round(float(y_pred.mean()), 6),
        "std_pred": round(float(y_pred.std()), 6),
    }


def compute_feature_importance(model, feature_names: list[str], top_n: int = 15) -> list[tuple[str, float]]:
    """Extract top feature importances."""
    if hasattr(model, "feature_importances_"):
        pairs = sorted(zip(feature_names, model.feature_importances_, strict=False), key=lambda x: x[1], reverse=True)
    else:
        pairs = list(zip(feature_names, [0.0] * len(feature_names), strict=False))
    return [(name, round(float(imp), 4)) for name, imp in pairs[:top_n]]


# ── JSON-safe conversion ────────────────────────────────────────────────────


def to_serializable(obj):
    """Convert numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_serializable(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(to_serializable(v) for v in obj)
    elif hasattr(obj, "item"):
        return obj.item()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return round(float(obj), 6)
    return obj


# ── Main training pipeline ──────────────────────────────────────────────────


def train_symbol(symbol: str, timeframe: str = "M15") -> dict:
    """Train dual-head models for a single symbol. Returns results dict."""
    logger.info("=" * 60)
    logger.info("TRAINING DUAL-HEAD MODELS: %s %s", symbol, timeframe)
    logger.info("=" * 60)

    # 1. Load features
    logger.info("\n[1/6] Loading features...")
    parquet_path = build_features_if_needed(symbol, timeframe)
    df = pd.read_parquet(parquet_path)
    logger.info("  Loaded: %d rows, %d columns", len(df), len(df.columns))

    # 2. Create labels
    logger.info("\n[2/6] Creating labels...")
    df = create_labels(df)
    logger.info("  After label creation: %d rows", len(df))

    # 3. Select feature columns
    feature_cols = get_feature_columns(df)
    logger.info("  Feature columns: %d", len(feature_cols))

    # Impute NaN features: forward-fill then zero-fill for remaining
    # SMC detectors produce sparse features (OB, sweeps, mitigation) —
    # dropping rows would eliminate >99% of the dataset.
    initial_nan_pct = df[feature_cols].isna().mean().mean() * 100
    df[feature_cols] = df[feature_cols].ffill()
    df[feature_cols] = df[feature_cols].fillna(0)
    final_nan_pct = df[feature_cols].isna().mean().mean() * 100
    logger.info("  NaN imputation: %.1f%% -> %.1f%% (ffill + zero-fill)", initial_nan_pct, final_nan_pct)

    X = df[feature_cols].values
    y_dir = df["target_direction"].values.astype(int)
    y_mag = df["target_magnitude"].values.astype(float)

    # 4. Time-based split: 70/15/15
    logger.info("\n[3/6] Time-based train/val/test split (70/15/15)...")
    n = len(X)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    X_train, y_dir_train, y_mag_train = X[:train_end], y_dir[:train_end], y_mag[:train_end]
    X_val, y_dir_val, y_mag_val = X[train_end:val_end], y_dir[train_end:val_end], y_mag[train_end:val_end]
    X_test, y_dir_test, y_mag_test = X[val_end:], y_dir[val_end:], y_mag[val_end:]

    logger.info("  Train: %d | Val: %d | Test: %d", len(X_train), len(X_val), len(X_test))
    logger.info("  Train period: first bar -> bar %d", train_end)
    logger.info("  Val period: bar %d -> %d", train_end, val_end)
    logger.info("  Test period: bar %d -> %d (end)", val_end, n)

    # 5. Purged k-fold CV on training data
    logger.info("\n[4/6] Purged k-fold CV (5 folds, embargo=5 bars)...")
    splits = purged_kfold_cv(X_train, y_dir_train, n_folds=5, embargo=5)
    cv_dir_metrics = []
    cv_mag_metrics = []

    for fold_idx, (tr_idx, va_idx) in enumerate(splits):
        X_tr, X_va = X_train[tr_idx], X_train[va_idx]
        y_dir_tr, y_dir_va = y_dir_train[tr_idx], y_dir_train[va_idx]
        y_mag_tr, y_mag_va = y_mag_train[tr_idx], y_mag_train[va_idx]

        # Direction
        m_dir = train_direction_head(X_tr, y_dir_tr, X_va, y_dir_va, feature_cols)
        y_dir_pred = m_dir.predict(X_va)
        fold_dir = compute_direction_metrics(y_dir_va, y_dir_pred)
        fold_dir["fold"] = fold_idx + 1
        cv_dir_metrics.append(fold_dir)

        # Magnitude
        m_mag = train_magnitude_head(X_tr, y_mag_tr, X_va, y_mag_va, feature_cols)
        y_mag_pred = m_mag.predict(X_va)
        fold_mag = compute_magnitude_metrics(y_mag_va, y_mag_pred)
        fold_mag["fold"] = fold_idx + 1
        cv_mag_metrics.append(fold_mag)

        logger.info(
            "  Fold %d: dir_acc=%.4f | mag_rmse=%.6f",
            fold_idx + 1,
            fold_dir["accuracy"],
            fold_mag["rmse"],
        )

    # Aggregate CV metrics
    cv_dir_avg = {
        "mean_accuracy": round(np.mean([m["accuracy"] for m in cv_dir_metrics]), 4),
        "std_accuracy": round(np.std([m["accuracy"] for m in cv_dir_metrics]), 4),
        "mean_f1": round(np.mean([m["f1"] for m in cv_dir_metrics]), 4),
        "folds": cv_dir_metrics,
    }
    cv_mag_avg = {
        "mean_rmse": round(np.mean([m["rmse"] for m in cv_mag_metrics]), 6),
        "std_rmse": round(np.std([m["rmse"] for m in cv_mag_metrics]), 6),
        "mean_r2": round(np.mean([m["r2"] for m in cv_mag_metrics]), 4),
        "folds": cv_mag_metrics,
    }
    logger.info(
        "  CV Direction: mean_acc=%.4f ± %.4f | mean_f1=%.4f",
        cv_dir_avg["mean_accuracy"],
        cv_dir_avg["std_accuracy"],
        cv_dir_avg["mean_f1"],
    )
    logger.info(
        "  CV Magnitude: mean_rmse=%.6f ± %.6f | mean_r2=%.4f",
        cv_mag_avg["mean_rmse"],
        cv_mag_avg["std_rmse"],
        cv_mag_avg["mean_r2"],
    )

    # 6. Train final models on train+val
    logger.info("\n[5/6] Training final models on train+val data...")
    X_trainval = np.concatenate([X_train, X_val])
    y_dir_trainval = np.concatenate([y_dir_train, y_dir_val])
    y_mag_trainval = np.concatenate([y_mag_train, y_mag_val])

    final_dir_model = train_direction_head(
        X_trainval,
        y_dir_trainval,
        X_test,
        y_dir_test,
        feature_cols,
    )
    final_mag_model = train_magnitude_head(
        X_trainval,
        y_mag_trainval,
        X_test,
        y_mag_test,
        feature_cols,
    )

    # 7. Evaluate on test set
    logger.info("\n[6/6] Evaluating on test set...")
    y_dir_test_pred = final_dir_model.predict(X_test)
    y_mag_test_pred = final_mag_model.predict(X_test)

    test_dir_metrics = compute_direction_metrics(y_dir_test, y_dir_test_pred)
    test_mag_metrics = compute_magnitude_metrics(y_mag_test, y_mag_test_pred)

    logger.info(
        "  Test Direction: acc=%.4f | prec=%.4f | rec=%.4f | f1=%.4f",
        test_dir_metrics["accuracy"],
        test_dir_metrics["precision"],
        test_dir_metrics["recall"],
        test_dir_metrics["f1"],
    )
    logger.info(
        "  Test Magnitude: rmse=%.6f | mae=%.6f | r2=%.4f",
        test_mag_metrics["rmse"],
        test_mag_metrics["mae"],
        test_mag_metrics["r2"],
    )

    # Feature importance
    dir_fi = compute_feature_importance(final_dir_model, feature_cols)
    mag_fi = compute_feature_importance(final_mag_model, feature_cols)

    # 8. Save models
    dir_model_path = MODELS_DIR / f"{symbol}_direction.pkl"
    mag_model_path = MODELS_DIR / f"{symbol}_magnitude.pkl"

    with open(dir_model_path, "wb") as f:
        pickle.dump(
            {
                "model": final_dir_model,
                "feature_columns": feature_cols,
                "symbol": symbol,
                "trained_at": datetime.now(UTC).isoformat(),
                "train_rows": len(X_trainval),
                "test_rows": len(X_test),
            },
            f,
        )
    logger.info("  Saved direction model: %s", dir_model_path.name)

    with open(mag_model_path, "wb") as f:
        pickle.dump(
            {
                "model": final_mag_model,
                "feature_columns": feature_cols,
                "symbol": symbol,
                "trained_at": datetime.now(UTC).isoformat(),
                "train_rows": len(X_trainval),
                "test_rows": len(X_test),
            },
            f,
        )
    logger.info("  Saved magnitude model: %s", mag_model_path.name)

    # 9. Save metrics
    report = {
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(UTC).isoformat(),
        "n_features": len(feature_cols),
        "n_rows": len(df),
        "split": {
            "train": len(X_train),
            "val": len(X_val),
            "test": len(X_test),
        },
        "cv_direction": cv_dir_avg,
        "cv_magnitude": cv_mag_avg,
        "test_direction": test_dir_metrics,
        "test_magnitude": test_mag_metrics,
        "feature_importance_direction": dir_fi,
        "feature_importance_magnitude": mag_fi,
    }

    metrics_path = REPORTS_DIR / f"model_training_{symbol}.json"
    with open(metrics_path, "w") as f:
        json.dump(to_serializable(report), f, indent=2)
    logger.info("  Saved metrics: %s", metrics_path.name)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS: %s", symbol)
    logger.info(
        "  Direction — CV acc: %.4f ± %.4f | Test acc: %.4f | F1: %.4f",
        cv_dir_avg["mean_accuracy"],
        cv_dir_avg["std_accuracy"],
        test_dir_metrics["accuracy"],
        test_dir_metrics["f1"],
    )
    logger.info(
        "  Magnitude — CV rmse: %.6f ± %.6f | Test rmse: %.6f | R²: %.4f",
        cv_mag_avg["mean_rmse"],
        cv_mag_avg["std_rmse"],
        test_mag_metrics["rmse"],
        test_mag_metrics["r2"],
    )
    logger.info("  Top direction features: %s", [f[0] for f in dir_fi[:5]])
    logger.info("  Top magnitude features: %s", [f[0] for f in mag_fi[:5]])
    logger.info("=" * 60)

    return report


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train per-asset dual-head models (direction + magnitude)",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Symbol to train, or ALL for all 4 target symbols",
    )
    parser.add_argument("--timeframe", default="M15", help="Timeframe (default M15)")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    symbols = TARGET_SYMBOLS if args.symbol.upper() == "ALL" else [args.symbol.upper()]

    results = {}
    for symbol in symbols:
        try:
            report = train_symbol(symbol, args.timeframe)
            results[symbol] = "OK"
        except Exception as e:
            logger.error("FAILED %s: %s", symbol, e, exc_info=True)
            results[symbol] = f"FAILED: {e}"

    # Final summary
    print("\n" + "=" * 60)
    print("BATCH TRAINING COMPLETE")
    for sym, status in results.items():
        print(f"  {sym}: {status}")
    print("=" * 60)

    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
