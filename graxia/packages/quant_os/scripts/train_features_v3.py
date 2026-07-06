"""
train_features_v3.py — Train XGBoost with features_v3 technical indicators.

Attempt #4 after ARCHIVE_NO_EDGE on old 17-feature set.
Uses: rsi_14, macd, macd_signal, macd_hist, bb_width, atr_ratio, adx_14,
      dist_ma_20, dist_ma_50, dist_ma_200, ret_1, ret_5, ret_10, atr_14,
      volume_ratio, high_low_pct, close_open_pct

If still no edge → PERMANENT ARCHIVE_NO_EDGE. No 5th attempt.
"""

import json
import math
import pickle
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import confusion_matrix

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cross_validation import combine_purged_k_fold_cv  # noqa: E402
from core.features import build_features  # noqa: E402


def edge_decision(test_acc: float, n_test: int, baseline: float = 0.5) -> str:
    """z-test for edge detection. Hard-coded decision rule."""
    se = math.sqrt(baseline * (1 - baseline) / n_test)
    if se == 0:
        return "ARCHIVE_NO_EDGE"
    z = (test_acc - baseline) / se
    if z > 1.96:  # 95% two-sided
        return "EDGE_CANDIDATE"
    return "ARCHIVE_NO_EDGE"


BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
MODEL_DIR = BASE / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ["XAUUSD", "EURUSD", "US30", "NAS100", "BTCUSD"]
TF = "M15"

# features_v3 technical indicators — canonical names from ml/pipeline.py FeatureEngineer
TECH_FEATURES = [
    "rsi_14",
    "rsi_14_normalized",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_width",
    "bb_position",
    "atr_ratio",
    "adx",
    "ema_20_dist",
    "ema_50_dist",
    "ema_200_dist",
]

# Basic price/volume features — canonical names
BASIC_FEATURES = [
    "return_1",
    "return_5",
    "return_10",
    "atr_14",
    "volume_ratio",
]

ALL_FEATURES = TECH_FEATURES + BASIC_FEATURES


def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """DEPRECATED: Technical indicators now provided by core.features.build_features.

    Kept for backward compatibility with any external callers.
    """
    from core.features import build_features as _bf

    return _bf(df)


def train_symbol(symbol: str) -> dict | None:
    csv_path = DATA_DIR / f"{symbol}_{TF}.csv"
    if not csv_path.exists():
        print(f"{symbol}: no data found")
        return None

    df = pd.read_csv(csv_path, parse_dates=["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = build_features(df)

    # Target: forward 5-bar return > 0.1% = 1, < -0.1% = 0, else skip
    df["fwd_ret"] = df["close"].shift(-5) / df["close"] - 1
    df["target"] = 0
    df.loc[df["fwd_ret"] > 0.001, "target"] = 1
    df.loc[df["fwd_ret"] < -0.001, "target"] = -1

    traded = df[df["target"] != 0].copy()
    traded["target"] = traded["target"].replace({-1: 0, 1: 1})

    # Filter to available features only
    feature_cols = [c for c in ALL_FEATURES if c in traded.columns]
    missing = [c for c in ALL_FEATURES if c not in traded.columns]
    if missing:
        print(f"{symbol}: WARNING — missing features: {missing}")

    X_all = traded[feature_cols].fillna(0).values
    y_all = traded["target"].values.astype(int)

    # CPCV
    n_bars = len(X_all)
    n_splits = 6
    n_test_splits = 2
    purged_size = 12
    embargo_size = 12

    paths = combine_purged_k_fold_cv(
        n_bars=n_bars,
        n_splits=n_splits,
        n_test_splits=n_test_splits,
        purged_size=purged_size,
        embargo_size=embargo_size,
        random_state=42,
    )

    fold_results = []
    best_model = None
    best_test_acc = -1.0

    for path_idx, path in enumerate(paths):
        for fold_idx, (train_idx, test_idx) in enumerate(path):
            if len(train_idx) < 50 or len(test_idx) < 10:
                continue

            X_train = X_all[train_idx]
            y_train = y_all[train_idx]
            X_test = X_all[test_idx]
            y_test = y_all[test_idx]

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=3,
                learning_rate=0.01,
                subsample=0.7,
                colsample_bytree=0.7,
                reg_lambda=5.0,
                reg_alpha=2.0,
                early_stopping_rounds=20,
                eval_metric="logloss",
                random_state=42,
                verbosity=0,
            )
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )

            train_acc = (model.predict(X_train) == y_train).mean()
            test_acc = (model.predict(X_test) == y_test).mean()

            y_pred = model.predict(X_test)
            cm = confusion_matrix(y_test, y_pred, labels=[0, 1])

            fold_results.append(
                {
                    "path": path_idx,
                    "fold": fold_idx,
                    "train_acc": float(train_acc),
                    "test_acc": float(test_acc),
                    "n_train": len(train_idx),
                    "n_test": len(test_idx),
                    "confusion_matrix": cm.tolist(),
                }
            )

            if test_acc > best_test_acc:
                best_test_acc = test_acc
                best_model = model

    if best_model is None:
        print(f"{symbol}: not enough data for CPCV")
        return None

    # Aggregate results
    avg_train = np.mean([r["train_acc"] for r in fold_results])
    avg_test = np.mean([r["test_acc"] for r in fold_results])
    total_n_test = sum(r["n_test"] for r in fold_results)

    agg_cm = np.zeros((2, 2), dtype=int)
    for r in fold_results:
        agg_cm += np.array(r["confusion_matrix"])

    edge_status = edge_decision(avg_test, total_n_test)
    z_se = math.sqrt(0.5 * 0.5 / total_n_test) if total_n_test > 0 else 0
    z_score = (avg_test - 0.5) / z_se if z_se > 0 else 0.0

    # Feature importance from best model
    importances = best_model.feature_importances_
    feat_imp = sorted(
        zip(feature_cols, importances.tolist(), strict=False),
        key=lambda x: x[1],
        reverse=True,
    )

    # Save model
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = MODEL_DIR / f"xgboost_v3_{symbol}_{timestamp}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(
            {
                "model": best_model,
                "feature_names": feature_cols,
                "train_acc": float(avg_train),
                "test_acc": float(avg_test),
                "symbol": symbol,
                "trained": timestamp,
                "cv_method": "CPCV",
                "n_folds": len(fold_results),
                "purged_size": purged_size,
                "embargo_size": embargo_size,
                "edge_status": edge_status,
                "z_score": float(z_score),
                "n_test": total_n_test,
                "feature_version": "v3",
            },
            f,
        )

    # Print results
    print(f"\n{'='*60}")
    print(f"{symbol}: features_v3 CPCV results")
    print(f"{'='*60}")
    print(f"  Train acc: {avg_train:.4f}")
    print(f"  Test acc:  {avg_test:.4f}")
    print(f"  n_test:    {total_n_test}")
    print(f"  z-score:   {z_score:.2f}")
    print(f"  Edge:      {edge_status}")
    print(f"  Features:  {len(feature_cols)}")
    print(f"  Folds:     {len(fold_results)}")
    print("\n  Confusion matrix (aggregated):")
    print(f"    TN={agg_cm[0,0]:>8,}  FP={agg_cm[0,1]:>8,}")
    print(f"    FN={agg_cm[1,0]:>8,}  TP={agg_cm[1,1]:>8,}")
    print("\n  Top 5 features by importance:")
    for name, imp in feat_imp[:5]:
        print(f"    {name:20s} {imp:.4f}")

    return {
        "symbol": symbol,
        "train_acc": float(avg_train),
        "test_acc": float(avg_test),
        "features": len(feature_cols),
        "feature_names": feature_cols,
        "bars": n_bars,
        "model_file": model_path.name,
        "cv_method": "CPCV",
        "n_folds": len(fold_results),
        "n_test": total_n_test,
        "z_score": float(z_score),
        "edge_status": edge_status,
        "confusion_matrix": agg_cm.tolist(),
        "feature_importance": feat_imp[:10],
        "fold_results": fold_results,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("features_v3 retrain — attempt #4")
    print(f"Features: {len(ALL_FEATURES)} total")
    print(f"  Technical: {TECH_FEATURES}")
    print(f"  Basic:     {BASIC_FEATURES}")
    print("=" * 60)

    results = []
    for sym in SYMBOLS:
        r = train_symbol(sym)
        if r:
            results.append(r)

    if not results:
        print("\nNo models trained. Check data files.")
        sys.exit(1)

    # Determine overall status with confusion matrix check
    overall_status = "ARCHIVE_NO_EDGE"
    warnings_list = []
    degenerate_count = 0

    for r in results:
        cm = np.array(r["confusion_matrix"])
        tn, fp = cm[0]
        fn, tp = cm[1]
        total = tn + fp + fn + tp

        # Check for degenerate model: predicts one class <1% of time
        class_0_pct = (tn + fp) / total if total > 0 else 0
        predict_0_pct = tn / (tn + fp) if (tn + fp) > 0 else 0
        if tn == 0 and fn == 0:
            degenerate_count += 1
            warnings_list.append(f"{r['symbol']}: DEGENERATE — never predicts class 0 (sell). TN=0, FN=0.")
        elif tn + fn < total * 0.01:
            degenerate_count += 1
            warnings_list.append(
                f"{r['symbol']}: DEGENERATE — predicts class 0 only {tn+fn:,} times out of {total:,} ({(tn+fn)/total*100:.2f}%)."
            )
        elif r.get("edge_status") == "EDGE_CANDIDATE":
            # Only consider non-degenerate EDGE_CANDIDATE
            overall_status = "EDGE_CANDIDATE"

    if degenerate_count > 0:
        warnings_list.append(f"{degenerate_count}/{len(results)} models are degenerate or near-degenerate.")

    # Even if z-test says EDGE_CANDIDATE, check if test accuracy is meaningful
    if overall_status == "EDGE_CANDIDATE":
        avg_acc = np.mean([r["test_acc"] for r in results])
        if avg_acc < 0.52:  # Less than 2% above random
            overall_status = "ARCHIVE_NO_EDGE"
            warnings_list.append(f"Average test accuracy {avg_acc:.4f} < 0.52 — within noise after costs.")
        # If majority of models are degenerate, no real edge
        if degenerate_count >= len(results) * 0.4:
            overall_status = "ARCHIVE_NO_EDGE"
            warnings_list.append(f"{degenerate_count}/{len(results)} models degenerate — no real edge found.")
        # If best non-degenerate model still < 52.5%, no edge
        non_degen_accs = [
            r["test_acc"]
            for r in results
            if not (np.array(r["confusion_matrix"])[0, 0] == 0 and np.array(r["confusion_matrix"])[1, 0] == 0)
        ]
        if non_degen_accs and max(non_degen_accs) < 0.525:
            overall_status = "ARCHIVE_NO_EDGE"
            warnings_list.append(
                f"Best non-degenerate accuracy {max(non_degen_accs):.4f} < 0.525 — no actionable edge."
            )

    # If still no edge, mark as PERMANENT
    if overall_status == "ARCHIVE_NO_EDGE":
        overall_status = "PERMANENT_ARCHIVE_NO_EDGE"
        warnings_list.append("features_v3 also fails. 4th attempt. Case permanently closed.")
        warnings_list.append("No more hyperparameter tuning. No 5th attempt.")

    # Write manifest
    manifest = {
        "version": "3.0",
        "feature_version": "v3",
        "generated": datetime.now().isoformat(),
        "cv_method": "CPCV",
        "attempt": 4,
        "models": [
            {
                "symbol": r["symbol"],
                "train_acc": r["train_acc"],
                "test_acc": r["test_acc"],
                "features": r["features"],
                "feature_names": r["feature_names"],
                "bars": r["bars"],
                "model_file": r["model_file"],
                "cv_method": r["cv_method"],
                "n_folds": r["n_folds"],
                "n_test": r["n_test"],
                "z_score": r["z_score"],
                "edge_status": r["edge_status"],
                "confusion_matrix": r["confusion_matrix"],
                "feature_importance": r["feature_importance"],
            }
            for r in results
        ],
        "overall_status": overall_status,
        "warnings": warnings_list,
    }

    manifest_path = MODEL_DIR / "manifest_v3.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Also update main manifest
    main_manifest_path = MODEL_DIR / "manifest.json"
    with open(main_manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Models trained: {len(results)}/{len(SYMBOLS)}")
    print(f"Overall status: {overall_status}")
    print()
    for r in results:
        cm = np.array(r["confusion_matrix"])
        tn, fp = cm[0]
        fn, tp = cm[1]
        print(
            f"  {r['symbol']:8s} acc={r['test_acc']:.4f} "
            f"z={r['z_score']:.2f} "
            f"TN={tn:>6,} FP={fp:>6,} FN={fn:>6,} TP={tp:>6,} "
            f"edge={r['edge_status']}"
        )
    print()
    if warnings_list:
        print("Warnings:")
        for w in warnings_list:
            print(f"  - {w}")

    print(f"\nManifest: {manifest_path}")
    print(f"Main manifest: {main_manifest_path}")
