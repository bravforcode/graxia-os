"""
Train a slippage prediction model from existing order training CSVs.
Handles both plain-English and α-encoded column headers.
Falls back to synthetic data if no real files are found.
"""

import os
import sys
import glob
import pickle
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "artifacts" / "mega_data" / "dataset"
MODEL_DIR = REPO_ROOT / "artifacts" / "mega_data" / "models"
MODEL_PATH = MODEL_DIR / "slippage_model.pkl"


HEADER_MAP = {
    "slippage_points": "slippage_points",
    "latency_ms": "latency_ms",
    "hist_spread_mean": "hist_spread_mean",
    "hist_tick_count": "hist_tick_count",
    "α3": "slippage_points",
    "α11": "latency_ms",
    "α1": "hist_spread_mean",
    "α5": "hist_tick_count",
}

TARGET_COL = "slippage_points"
FEATURE_COLS = ["latency_ms", "hist_spread_mean", "hist_tick_count"]

N_SAMPLES_SYNTHETIC = 5000
RANDOM_STATE = 42


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Rename α-encoded headers to English names when needed."""
    rename = {k: v for k, v in HEADER_MAP.items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _find_csv_files() -> list[Path]:
    files = sorted(Path(DATASET_DIR).glob("*.csv"))
    return files


def _load_real_data() -> pd.DataFrame | None:
    csv_files = _find_csv_files()
    if not csv_files:
        return None

    chunks = []
    for p in csv_files:
        try:
            chunk = pd.read_csv(p)
            chunk = _normalise_headers(chunk)
            needed = {TARGET_COL, "symbol", "side"} | set(FEATURE_COLS)
            if needed.issubset(chunk.columns):
                chunks.append(chunk)
        except Exception:
            continue

    if not chunks:
        return None

    df = pd.concat(chunks, ignore_index=True)
    df = df.dropna(subset=list(needed))
    return df


def _make_synthetic_data() -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_STATE)
    symbols = ["EURUSD", "XAUUSD", "GBPUSD"]
    sides = ["BUY", "SELL"]

    n = N_SAMPLES_SYNTHETIC
    data = {
        "symbol": rng.choice(symbols, size=n),
        "side": rng.choice(sides, size=n),
        "latency_ms": rng.exponential(200, size=n).clip(1, 2000),
        "hist_spread_mean": rng.exponential(0.5, size=n).clip(0.00001, 5.0),
        "hist_tick_count": rng.poisson(50000, size=n).clip(100, 500000),
    }
    df = pd.DataFrame(data)

    base_slippage = (
        df["latency_ms"] * 0.002
        + df["hist_spread_mean"] * 3.0
        + (df["hist_tick_count"] < 10000).astype(int) * 2.0
        + (df["side"] == "SELL").astype(int) * 0.5
        + rng.normal(0, 0.5, size=n)
    )

    symbol_noise = rng.normal(0, 0.3, size=n)
    symbol_noise += (df["symbol"] == "XAUUSD").astype(int) * 1.0
    symbol_noise += (df["symbol"] == "GBPUSD").astype(int) * 0.3

    df["slippage_points"] = (base_slippage + symbol_noise).clip(-5, 20).round(2)
    return df


def _prep_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    y = df[TARGET_COL].values

    le_symbol = LabelEncoder()
    symbol_enc = le_symbol.fit_transform(df["symbol"])

    side_enc = (df["side"].str.upper() == "SELL").astype(int).values

    X_list = [df[c].values for c in FEATURE_COLS]
    X_arr = np.column_stack([symbol_enc, side_enc] + X_list)
    feature_names = ["symbol_enc"] + ["side"] + FEATURE_COLS

    return X_arr, y, feature_names, le_symbol


def train():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df_real = _load_real_data()
    if df_real is not None and len(df_real) >= 100:
        print(f"Loaded {len(df_real)} real samples from {DATASET_DIR}")
        df = df_real
        source = "real"
    else:
        print("No real training data found — generating synthetic dataset for demo.")
        df = _make_synthetic_data()
        source = "synthetic"

    X, y, feature_names, le_symbol = _prep_features(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE
    )

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "label_encoder": le_symbol, "feature_names": feature_names}, f)

    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])
    top3 = feat_imp[:3]

    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)}
    summary = {
        "source": source,
        "training_samples": len(df),
        "metrics": metrics,
        "feature_importances": {k: round(v, 4) for k, v in feat_imp},
    }
    summary_path = MODEL_DIR / "training_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSource:          {source} ({len(df)} samples)")
    print(f"Model saved to:  {MODEL_PATH}")
    print(f"MAE:             {mae:.4f}")
    print(f"RMSE:            {rmse:.4f}")
    print(f"R²:              {r2:.4f}")
    print(f"\nFeature importance:")
    for name, imp in feat_imp:
        print(f"  {name}: {imp:.4f}")

    return metrics, top3


if __name__ == "__main__":
    metrics, top3 = train()
    print(f"\n{'='*50}")
    print("TRAINING COMPLETE")
