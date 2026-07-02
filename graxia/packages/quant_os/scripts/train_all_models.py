"""
train_all_models.py — Train XGBoost for every symbol using CPCV
"""

import json
import pickle
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings("ignore")

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.cross_validation import combine_purged_k_fold_cv

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
MODEL_DIR = BASE / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT_PATH = (
    Path("/logs/trainer_heartbeat") if Path("/logs").exists() else BASE / "data" / "logs" / "trainer_heartbeat"
)

SYMBOLS = ["XAUUSD", "EURUSD", "US30", "NAS100", "BTCUSD"]
TF = "M15"


def build_features(df):
    df = df.copy()
    df["ret_1"] = df["close"].pct_change(1)
    df["ret_5"] = df["close"].pct_change(5)
    df["ret_10"] = df["close"].pct_change(10)
    df["ma_5"] = df["close"].rolling(5).mean()
    df["ma_10"] = df["close"].rolling(10).mean()
    df["ma_20"] = df["close"].rolling(20).mean()
    df["ma_50"] = df["close"].rolling(50).mean()
    df["ratio_ma5_ma20"] = df["ma_5"] / df["ma_20"]
    df["ratio_ma10_ma50"] = df["ma_10"] / df["ma_50"]
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(), (df["low"] - df["close"].shift()).abs()],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))
    df["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    for col in ["close", "volume", "atr_14"]:
        if col in df.columns:
            df[f"{col}_zscore"] = (df[col] - df[col].rolling(20).mean()) / df[col].rolling(20).std().replace(0, np.nan)
    df["high_low_pct"] = (df["high"] - df["low"]) / df["close"]
    df["close_open_pct"] = (df["close"] - df["open"]) / df["open"]
    return df


def train_symbol(symbol):
    csv_path = DATA_DIR / f"{symbol}_{TF}.csv"
    if not csv_path.exists():
        print(f"{symbol}: no data found")
        return None

    df = pd.read_csv(csv_path, parse_dates=["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = build_features(df)

    df["fwd_ret"] = df["close"].shift(-5) / df["close"] - 1
    df["target"] = 0
    df.loc[df["fwd_ret"] > 0.001, "target"] = 1
    df.loc[df["fwd_ret"] < -0.001, "target"] = -1

    traded = df[df["target"] != 0].copy()
    traded["target"] = traded["target"].replace({-1: 0, 1: 1})

    feature_cols = [
        c
        for c in traded.columns
        if c.startswith(("ret_", "ma_", "ratio_", "atr_", "rsi_", "volume_", "close_", "high_low", "close_open"))
    ]

    X_all = traded[feature_cols].fillna(0).values
    y_all = traded["target"].values.astype(int)

    # CPCV: purged + embargoed cross-validation (no simple iloc[:split])
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
    best_feature_cols = feature_cols

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

            fold_results.append(
                {
                    "path": path_idx,
                    "fold": fold_idx,
                    "train_acc": float(train_acc),
                    "test_acc": float(test_acc),
                    "n_train": len(train_idx),
                    "n_test": len(test_idx),
                }
            )

            if test_acc > best_test_acc:
                best_test_acc = test_acc
                best_model = model

    if best_model is None:
        print(f"{symbol}: not enough data for CPCV")
        return None

    # Use best model across all CPCV folds
    avg_train = np.mean([r["train_acc"] for r in fold_results])
    avg_test = np.mean([r["test_acc"] for r in fold_results])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = MODEL_DIR / f"xgboost_{symbol}_{timestamp}.pkl"
    with open(path, "wb") as f:
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
            },
            f,
        )

    print(
        f"{symbol:6s}: CPCV avg_train={avg_train:.4f} avg_test={avg_test:.4f} features={len(feature_cols)} folds={len(fold_results)} -> {path.name}"
    )
    return {
        "symbol": symbol,
        "train_acc": float(avg_train),
        "test_acc": float(avg_test),
        "features": len(feature_cols),
        "bars": n_bars,
        "model_file": path.name,
        "cv_method": "CPCV",
        "n_folds": len(fold_results),
    }


if __name__ == "__main__":

    def _write_heartbeat():
        """Write heartbeat file for Docker healthcheck."""
        try:
            HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_PATH.write_text(datetime.now().isoformat())
        except Exception:
            pass

    _write_heartbeat()
    results = []
    for sym in SYMBOLS:
        r = train_symbol(sym)
        if r:
            results.append(r)
        _write_heartbeat()  # update after each symbol
    print(f"\nTrained {len(results)}/{len(SYMBOLS)} models")
    json.dump(results, open(MODEL_DIR / "training_results.json", "w"), indent=2)
    _write_heartbeat()  # final heartbeat
