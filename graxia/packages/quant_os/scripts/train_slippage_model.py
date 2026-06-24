"""Train a slippage prediction model from order training CSVs / Parquets.

Handles both plain-English and α-encoded column headers.
Falls back to synthetic data if no real files are found.
Includes model caching: re-trains only when source data changes.
"""

import hashlib
import json
import pickle
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "artifacts" / "mega_data" / "dataset"
MODEL_DIR = REPO_ROOT / "artifacts" / "mega_data" / "models"
MODEL_PATH = MODEL_DIR / "slippage_model.pkl"
CACHE_HASH_PATH = MODEL_DIR / "data_hash.txt"
METRICS_PATH = MODEL_DIR / "metrics.json"
SUMMARY_PATH = MODEL_DIR / "training_summary.json"

HEADER_MAP = {
    "slippage_points": "slippage_points",
    "latency_ms": "latency_ms",
    "hist_spread_mean": "hist_spread_mean",
    "hist_spread_std": "hist_spread_std",
    "hist_spread_max": "hist_spread_max",
    "hist_tick_count": "hist_tick_count",
    "α3": "slippage_points",
    "α11": "latency_ms",
    "α1": "hist_spread_mean",
    "α5": "hist_tick_count",
}

TARGET_COL = "slippage_points"

BASE_FEATURES = [
    "latency_ms",
    "hist_spread_mean",
    "hist_spread_std",
    "hist_spread_max",
    "hist_tick_count",
]

DERIVED_FEATURES = {
    "spread_price": lambda df: df["hist_spread_mean"] * 10000,
    "deviation_used": lambda df: df["hist_spread_std"] / (df["hist_spread_mean"] + 1e-10),
    "spread_points": lambda df: df["hist_spread_max"] / (df["hist_spread_mean"] + 1e-10),
}

ALL_FEATURES = list(BASE_FEATURES) + list(DERIVED_FEATURES.keys())

N_SAMPLES_SYNTHETIC = 5000
RANDOM_STATE = 42


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Rename α-encoded headers to English names when needed."""
    rename = {k: v for k, v in HEADER_MAP.items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _find_data_files() -> list[Path]:
    csvs = sorted(DATASET_DIR.glob("*.csv"))
    pars = sorted(DATASET_DIR.glob("*.parquet"))
    return csvs + pars


def _compute_data_hash(files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        h.update(p.name.encode())
        h.update(str(p.stat().st_size).encode())
        h.update(str(p.stat().st_mtime).encode())
    return h.hexdigest()


def _read_file(p: Path) -> pd.DataFrame | None:
    try:
        if p.suffix == ".parquet":
            return pd.read_parquet(p)
        return pd.read_csv(p)
    except Exception as e:
        print(f"  Warning: skipping {p.name} — {e}")
        return None


def _load_real_data() -> pd.DataFrame | None:
    files = _find_data_files()
    if not files:
        return None

    needed = {TARGET_COL, "symbol", "side"} | set(BASE_FEATURES)
    chunks = []
    for p in files:
        chunk = _read_file(p)
        if chunk is None:
            continue
        chunk = _normalise_headers(chunk)
        missing = needed - set(chunk.columns)
        if missing:
            print(f"  Skipping {p.name} — missing columns: {missing}")
            continue
        chunks.append(chunk)

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
        "hist_spread_std": rng.exponential(0.1, size=n).clip(0.00001, 1.0),
        "hist_spread_max": rng.exponential(1.0, size=n).clip(0.00001, 10.0),
        "hist_tick_count": rng.poisson(50000, size=n).clip(100, 500000),
    }
    df = pd.DataFrame(data)
    base = (
        df["latency_ms"] * 0.002
        + df["hist_spread_mean"] * 3.0
        + (df["hist_tick_count"] < 10000).astype(int) * 2.0
        + (df["side"] == "SELL").astype(int) * 0.5
        + rng.normal(0, 0.5, size=n)
    )
    noise = rng.normal(0, 0.3, size=n)
    noise += (df["symbol"] == "XAUUSD").astype(int) * 1.0
    noise += (df["symbol"] == "GBPUSD").astype(int) * 0.3
    df["slippage_points"] = (base + noise).clip(-5, 20).round(2)
    for name, fn in DERIVED_FEATURES.items():
        df[name] = fn(df)
    return df


def _prep_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str], LabelEncoder]:
    le = LabelEncoder()
    symbol_enc = le.fit_transform(df["symbol"])
    side_enc = (df["side"].str.upper() == "SELL").astype(int).values
    base_arr = np.column_stack([df[c].values for c in BASE_FEATURES])
    derived_arr = np.column_stack([df[name].values for name in DERIVED_FEATURES])
    X = np.column_stack([symbol_enc, side_enc, base_arr, derived_arr])
    names = ["symbol_enc", "side"] + ALL_FEATURES
    y = df[TARGET_COL].values
    return X, y, names, le


def train():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df_real = _load_real_data()
    if df_real is not None and len(df_real) >= 100:
        print(f"Loaded {len(df_real)} real samples from {DATASET_DIR}")
        df = df_real
        src = "real"
        files = _find_data_files()
        data_hash = _compute_data_hash(files)
        if MODEL_PATH.exists() and CACHE_HASH_PATH.exists():
            cached = CACHE_HASH_PATH.read_text().strip()
            if cached == data_hash and SUMMARY_PATH.exists():
                print("Model cache is fresh — using cached model. Skipping training.")
                summary = json.loads(SUMMARY_PATH.read_text())
                feat_imps = list(summary["feature_importances"].items())
                print(f"Samples: {summary['training_samples']}  Features: {summary['feature_count']}")
                print(f"MAE: {summary['metrics']['mae']}  RMSE: {summary['metrics']['rmse']}  R²: {summary['metrics']['r2']}")
                print("\nTop 5 features:")
                for name, imp in feat_imps[:5]:
                    print(f"  {name}: {imp}")
                return summary["metrics"], feat_imps[:3]
    else:
        print("No real training data found — generating synthetic dataset for demo.")
        df = _make_synthetic_data()
        src = "synthetic"
        data_hash = None

    for name, fn in DERIVED_FEATURES.items():
        if name not in df.columns:
            df[name] = fn(df)

    X, y, feature_names, le = _prep_features(df)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE)

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr)

    y_pred = model.predict(X_te)
    mae = mean_absolute_error(y_te, y_pred)
    rmse = np.sqrt(mean_squared_error(y_te, y_pred))
    r2 = r2_score(y_te, y_pred)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "label_encoder": le, "feature_names": feature_names}, f)

    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])
    top5 = feat_imp[:5]

    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)}

    summary = {
        "source": src,
        "training_samples": len(df),
        "feature_count": len(feature_names),
        "metrics": metrics,
        "feature_importances": {k: round(v, 4) for k, v in feat_imp},
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    if data_hash:
        CACHE_HASH_PATH.write_text(data_hash)
    for sp in [SUMMARY_PATH, METRICS_PATH]:
        with open(sp, "w") as f:
            json.dump(summary, f, indent=2)

    print(f"\nSource:           {src}")
    print(f"Samples:          {len(df)}")
    print(f"Features:         {len(feature_names)}")
    print(f"Model saved to:   {MODEL_PATH}")
    print(f"MAE:              {mae:.4f}")
    print(f"RMSE:             {rmse:.4f}")
    print(f"R²:               {r2:.4f}")
    print("\nTop 5 features by importance:")
    for name, imp in top5:
        print(f"  {name}: {imp:.4f}")

    return metrics, list(feat_imp[:3])


if __name__ == "__main__":
    metrics, top3 = train()
    print(f"\n{'='*50}")
    print("TRAINING COMPLETE")
