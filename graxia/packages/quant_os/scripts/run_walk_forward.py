#!/usr/bin/env python3
"""
WALK-FORWARD RE-RUN PIPELINE — Full run from warehouse/CSV data to verdict.

Reads OHLCV data, builds features, runs walk-forward validation with cost
backtest, compares against previous results, and generates a verdict.

Usage:
    python scripts/run_walk_forward.py --symbol EURUSD --timeframe M15
    python scripts/run_walk_forward.py --symbol XAUUSD --quick
    python scripts/run_walk_forward.py --symbol EURUSD --timeframe M15 --verbose
"""

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from datetime import datetime, UTC
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE, "scripts")

DEFAULT_DATA_DIR = os.path.join(BASE, "data")
DEFAULT_FEAT_DIR = os.path.join(BASE, "artifacts", "features")
DEFAULT_FEAT_V2_DIR = os.path.join(BASE, "artifacts", "features_v2")
DEFAULT_LABEL_DIR = os.path.join(BASE, "artifacts", "labels")
DEFAULT_WF_DIR = os.path.join(BASE, "artifacts", "walk_forward")
DEFAULT_OUT_DIR = os.path.join(BASE, "artifacts", "walk_forward_v2")
DEFAULT_DUCKDB_PATH = os.path.join(BASE, "data", "warehouse", "quantos.duckdb")

FREQ_PD: dict[str, str] = {
    "M1": "1min", "M5": "5min", "M15": "15min",
    "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1d",
}

VERDICT_LABELS = [
    "PASS_TO_NEXT_PHASE",
    "CONDITIONAL_PASS",
    "NEGATIVE_EDGE_CONFIRMED",
    "INSUFFICIENT_SAMPLE",
    "ARCHIVE_NO_EDGE",
]


# ─── Phase 1: Data Loading ────────────────────────────────────────────────

def load_ohlcv_from_csv(
    data_dir: str, symbol: str, freq: str,
    start: str | None = None, end: str | None = None,
) -> pd.DataFrame:
    csv_path = os.path.join(data_dir, f"{symbol}_{freq}.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"OHLCV CSV not found: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["time"])
    df = df.rename(columns={"time": "timestamp"})
    df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz="UTC")]
    df = df.sort_index().drop_duplicates()
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {missing}")
    return df


def load_ohlcv_from_parquet(
    data_dir: str, symbol: str, freq: str,
    start: str | None = None, end: str | None = None,
) -> pd.DataFrame:
    from glob import glob as glob_glob

    # Hive-partitioned: symbol={sym}/frequency={freq}/**/*.parquet
    hive_pattern = os.path.join(data_dir, "**", "ohlcv",
                                f"symbol={symbol}", f"frequency={freq}",
                                "**", "*.parquet")
    paths = sorted(glob_glob(hive_pattern, recursive=True))

    # Fallback: flat files named *{symbol}_{freq}*.parquet
    if not paths:
        flat_patterns = [
            os.path.join(data_dir, "**", f"*{symbol}_{freq}*.parquet"),
            os.path.join(data_dir, "**", f"*{symbol}*{freq}*.parquet"),
            os.path.join(data_dir, "**", f"*{symbol}*.parquet"),
        ]
        for pat in flat_patterns:
            paths = sorted(glob_glob(pat, recursive=True))
            if paths:
                break

    if not paths:
        raise FileNotFoundError(f"No parquet files for {symbol} @ {freq} in {data_dir}")

    dfs = []
    for p in paths:
        df = pd.read_parquet(p)
        # Normalise time column
        time_col = "time" if "time" in df.columns and "timestamp" not in df.columns else "timestamp"
        if time_col in df.columns:
            df = df.set_index(time_col)
        df.index = pd.to_datetime(df.index, utc=True)
        # Keep only OHLCV columns
        keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[keep]
        dfs.append(df)
    combined = pd.concat(dfs).sort_index().drop_duplicates()
    if start:
        combined = combined[combined.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        combined = combined[combined.index <= pd.Timestamp(end, tz="UTC")]
    print(f"  [OK] Loaded {len(combined)} bars from Parquet ({time.time()-t0:.1f}s)")
    return combined


def load_ohlcv_from_duckdb(
    db_path: str, symbol: str, freq: str,
    start: str | None = None, end: str | None = None,
) -> pd.DataFrame:
    try:
        import duckdb
    except ImportError:
        raise ImportError("duckdb not installed. Use --data-dir for CSV/parquet instead.")
    conn = duckdb.connect(db_path)

    # Try named table first (ohlcv_XAUUSD_M15), then generic ohlcv table
    named_table = f"ohlcv_{symbol}_{freq}"
    tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    if named_table in tables:
        table = named_table
        time_col = "timestamp"
    elif "ohlcv" in tables:
        # Generic warehouse table with symbol/frequency columns
        time_col = "time"
        conditions = [f"symbol = '{symbol}'", f"frequency = '{freq}'"]
        if start:
            conditions.append(f"\"{time_col}\" >= '{start}'")
        if end:
            conditions.append(f"\"{time_col}\" <= '{end}'")
        query = f'SELECT "{time_col}" AS timestamp, open, high, low, close, volume FROM ohlcv WHERE {" AND ".join(conditions)} ORDER BY "{time_col}"'
        df = conn.execute(query).fetchdf()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
        conn.close()
        return df
    else:
        candidates = [t for t in tables if symbol.lower() in t.lower()]
        if not candidates:
            raise ValueError(f"No table found for {symbol} in DuckDB. Available: {tables}")
        table = candidates[0]
        time_col = "timestamp"

    query = f'SELECT "{time_col}" AS timestamp, open, high, low, close, volume FROM "{table}"'
    conditions = []
    if start:
        conditions.append(f"\"{time_col}\" >= '{start}'")
    if end:
        conditions.append(f"\"{time_col}\" <= '{end}'")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += f' ORDER BY "{time_col}"'
    df = conn.execute(query).fetchdf()
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    conn.close()
    return df


def load_ohlcv(
    data_dir: str, symbol: str, freq: str,
    start: str | None = None, end: str | None = None,
    db_path: str | None = None,
) -> pd.DataFrame:
    if db_path and os.path.exists(db_path):
        t0 = time.time()
        df = load_ohlcv_from_duckdb(db_path, symbol, freq, start, end)
        print(f"  [OK] Loaded {len(df)} bars from DuckDB ({time.time()-t0:.1f}s)")
        return df
    try:
        t0 = time.time()
        df = load_ohlcv_from_parquet(data_dir, symbol, freq, start, end)
        print(f"  [OK] Loaded {len(df)} bars from Parquet ({time.time()-t0:.1f}s)")
        return df
    except FileNotFoundError:
        pass
    t0 = time.time()
    df = load_ohlcv_from_csv(data_dir, symbol, freq, start, end)
    print(f"  [OK] Loaded {len(df)} bars from CSV ({time.time()-t0:.1f}s)")
    return df


# ─── Phase 2: Feature Engineering ─────────────────────────────────────────

def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["return_1"] = result["close"].pct_change(1)
    result["return_5"] = result["close"].pct_change(5)
    result["return_15"] = result["close"].pct_change(15)
    result["log_return"] = np.log(result["close"] / result["close"].shift(1))
    result["high_minus_low"] = result["high"] - result["low"]
    result["close_position"] = (result["close"] - result["low"]) / (result["high"] - result["low"] + 1e-10)
    result["volatility_5"] = result["return_1"].rolling(5).std()
    result["volatility_15"] = result["return_1"].rolling(15).std()
    tr = pd.concat([
        result["high"] - result["low"],
        (result["high"] - result["close"].shift(1)).abs(),
        (result["low"] - result["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    result["tr"] = tr
    result["atr_5"] = tr.rolling(5).mean()
    result["atr_15"] = tr.rolling(15).mean()
    delta = result["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    result["rsi_14"] = 100 - (100 / (1 + rs))
    ema12 = result["close"].ewm(span=12).mean()
    ema26 = result["close"].ewm(span=26).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]
    result["bb_mid"] = result["close"].rolling(20).mean()
    result["bb_std"] = result["close"].rolling(20).std()
    result["bb_upper"] = result["bb_mid"] + 2 * result["bb_std"]
    result["bb_lower"] = result["bb_mid"] - 2 * result["bb_std"]
    result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / result["bb_mid"]
    result["bb_position"] = (result["close"] - result["bb_lower"]) / (result["bb_upper"] - result["bb_lower"] + 1e-10)
    result["sma_5"] = result["close"].rolling(5).mean()
    result["sma_20"] = result["close"].rolling(20).mean()
    result["sma_ratio"] = result["sma_5"] / result["sma_20"]
    result["target"] = (result["close"].shift(-1) > result["close"]).astype(int)
    result["target_return"] = result["return_1"].shift(-1)
    nan_cols = [c for c in result.columns if result[c].isna().all()]
    result = result.drop(columns=nan_cols)
    return result.dropna()


def add_session_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["hour"] = result.index.hour
    result["minute"] = result.index.minute
    result["day_of_week"] = result.index.dayofweek
    result["is_asian"] = ((result["hour"] >= 0) & (result["hour"] < 8)).astype(int)
    result["is_london"] = ((result["hour"] >= 8) & (result["hour"] < 17)).astype(int)
    result["is_ny"] = ((result["hour"] >= 13) & (result["hour"] < 22)).astype(int)
    result["is_overlap"] = ((result["hour"] >= 13) & (result["hour"] < 17)).astype(int)
    return result


def add_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "volatility_15" not in result.columns:
        return result
    vol = result["volatility_15"]
    vol_percentile = vol.rolling(100, min_periods=20).rank(pct=True)
    result["vol_percentile"] = vol_percentile
    result["vol_regime"] = np.where(
        vol_percentile > 0.8, 2,
        np.where(vol_percentile > 0.5, 1, 0)
    )
    result["vol_regime"] = result["vol_regime"].fillna(1).astype(int)
    if "atr_5" in result.columns:
        atr_ma = result["atr_5"].rolling(50).mean()
        result["atr_ratio"] = result["atr_5"] / (atr_ma + 1e-10)
    return result


def save_features_v1(df: pd.DataFrame, feat_dir: str, symbol: str, freq_pd: str):
    os.makedirs(feat_dir, exist_ok=True)
    path = os.path.join(feat_dir, f"features_{symbol}_{freq_pd}.parquet")
    save_df = df.reset_index()
    save_df.to_parquet(path)
    return path


def save_features_v2(df: pd.DataFrame, feat_v2_dir: str, symbol: str, freq_pd: str):
    os.makedirs(feat_v2_dir, exist_ok=True)
    path = os.path.join(feat_v2_dir, f"features_v2_{symbol}_{freq_pd}.parquet")
    save_df = df.reset_index()
    save_df.to_parquet(path)
    return path


def build_features_pipeline(
    df: pd.DataFrame, symbol: str, freq: str, freq_pd: str,
    feat_dir: str, feat_v2_dir: str,
    feature_groups: list[str],
) -> pd.DataFrame:
    t0 = time.time()
    features = compute_technical_features(df)
    print(f"  Technical features: {len(features)} rows x {len(features.columns)} cols")

    if "session" in feature_groups:
        features = add_session_features(features)
        print(f"  Session features added: {len(features.columns)} total cols")

    if "regime" in feature_groups:
        features = add_regime_features(features)
        print(f"  Regime features added: {len(features.columns)} total cols")

    features["symbol"] = symbol
    features["freq"] = freq_pd

    feat_path = save_features_v1(features, feat_dir, symbol, freq_pd)
    print(f"  Saved v1 features: {feat_path}")

    feat_v2_path = save_features_v2(features, feat_v2_dir, symbol, freq_pd)
    print(f"  Saved v2 features: {feat_v2_path} ({time.time()-t0:.1f}s)")

    return features


def run_advanced_features(symbol: str, freq_pd: str, feat_dir: str, feat_v2_dir: str, verbose: bool) -> bool:
    t0 = time.time()
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "features_advanced.py"),
        "--mode", "all",
        "--symbols", symbol,
        "--freqs", freq_pd,
        "--main-tf", freq_pd,
        "--higher-tfs", "1h,4h",
        "--feat-dir", feat_dir,
        "--output", feat_v2_dir,
    ]
    if verbose:
        print(f"  [CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  [WARN] Advanced features step exited {result.returncode}")
        if verbose:
            print(f"  stderr: {result.stderr}")
        return False
    if verbose:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    print(f"  Advanced features complete ({time.time()-t0:.1f}s)")
    return True


# ─── Phase 3: Labels ──────────────────────────────────────────────────────

def run_triple_barrier_labels(
    symbol: str, freq_pd: str, feat_dir: str, label_dir: str, verbose: bool
) -> bool:
    t0 = time.time()
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "label_triple_barrier.py"),
        "--symbol", symbol,
        "--freq", freq_pd,
        "--method", "dynamic",
        "--k-upper", "2.0",
        "--k-lower", "2.0",
        "--max-bars", "20",
        "--output", label_dir,
    ]
    if verbose:
        print(f"  [CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  [WARN] Label step exited {result.returncode}")
        if verbose:
            print(f"  stderr: {result.stderr}")
        return False
    if verbose:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    print(f"  Triple-barrier labels complete ({time.time()-t0:.1f}s)")

    try:
        label_path = os.path.join(label_dir, f"labels_{symbol}_{freq_pd}.parquet")
        if os.path.exists(label_path):
            labels = pd.read_parquet(label_path)
            print(f"  Labels: {len(labels)} bars, "
                  f"+1={int((labels['tb_label']==1).sum())} "
                  f"-1={int((labels['tb_label']==-1).sum())} "
                  f"0={int((labels['tb_label']==0).sum())}"
                  if "tb_label" in labels.columns else f"  Labels loaded: {len(labels)} rows")
    except Exception as e:
        print(f"  [WARN] Could not read label output: {e}")
    return True


# ─── Phase 4: Walk-Forward Execution ──────────────────────────────────────

def run_walk_forward(
    symbol: str, freq_pd: str, train_window: int, test_window: int, step: int,
    spread_cost: float, slippage_p90: float, min_confidence: float,
    max_depth: int, n_estimators: int, output_dir: str, seed: int, verbose: bool,
    cost_config: str | None = None,
) -> dict | None:
    t0 = time.time()
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "walk_forward.py"),
        "--symbol", symbol,
        "--freq", freq_pd,
        "--train-window", str(train_window),
        "--test-window", str(test_window),
        "--step", str(step),
        "--spread-cost", str(spread_cost),
        "--slippage-p90", str(slippage_p90),
        "--min-confidence", str(min_confidence),
        "--max-depth", str(max_depth),
        "--n-estimators", str(n_estimators),
    ]
    if cost_config and os.path.exists(cost_config):
        cmd.extend(["--cost-config", cost_config])
    cmd.extend(["--output", output_dir])
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE + os.pathsep + env.get("PYTHONPATH", "")
    if seed is not None:
        env["PYTHONHASHSEED"] = str(seed)
    if verbose:
        print(f"  [CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    if result.returncode != 0:
        print(f"  [ERROR] Walk-forward exited {result.returncode}")
        if verbose:
            print(f"  stderr: {result.stderr}")
        return None
    if verbose:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    print(f"  Walk-forward complete ({time.time()-t0:.1f}s)")

    result_path = os.path.join(
        output_dir,
        f"wf_{symbol}_{freq_pd}_{train_window}w_{test_window}t_conf{min_confidence}.json",
    )
    if os.path.exists(result_path):
        with open(result_path) as f:
            return json.load(f)
    alt_pattern = f"wf_{symbol}_{freq_pd}*.json"
    from glob import glob
    alt_files = glob(os.path.join(output_dir, alt_pattern))
    if alt_files:
        with open(sorted(alt_files)[-1]) as f:
            return json.load(f)
    print(f"  [WARN] Walk-forward result not found at {result_path}")
    return None


# ─── Phase 5: Cost Backtest ───────────────────────────────────────────────

def run_cost_backtest(
    symbol: str, freq_pd: str, spread_cost: float, slippage_p90: float,
    output_dir: str, verbose: bool,
    cost_config: str | None = None,
) -> dict | None:
    t0 = time.time()
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "backtest_cost.py"),
        "--symbol", symbol,
        "--freq", freq_pd,
        "--spread-cost", str(spread_cost),
        "--slippage-p90", str(slippage_p90),
    ]
    if cost_config and os.path.exists(cost_config):
        cmd.extend(["--cost-config", cost_config])
    cmd.extend(["--output", output_dir])
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE + os.pathsep + env.get("PYTHONPATH", "")
    if verbose:
        print(f"  [CMD] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    if result.returncode != 0:
        print(f"  [WARN] Cost backtest exited {result.returncode}")
        if verbose:
            print(f"  stderr: {result.stderr}")
        return None
    if verbose:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    print(f"  Cost backtest complete ({time.time()-t0:.1f}s)")

    result_path = os.path.join(output_dir, f"backtest_{symbol}_{freq_pd}.json")
    if os.path.exists(result_path):
        with open(result_path) as f:
            return json.load(f)
    return None


# ─── Phase 6: Comparison ─────────────────────────────────────────────────

def find_previous_result(
    wf_dir: str, symbol: str, freq_pd: str,
) -> dict | None:
    from glob import glob
    pattern = os.path.join(wf_dir, f"wf_{symbol}_{freq_pd}*.json")
    files = sorted(glob(pattern))
    if not files:
        return None
    try:
        with open(files[-1]) as f:
            return json.load(f)
    except Exception:
        return None


def format_previous_path(wf_dir: str, symbol: str, freq_pd: str) -> str:
    from glob import glob
    pattern = os.path.join(wf_dir, f"wf_{symbol}_{freq_pd}*.json")
    files = sorted(glob(pattern))
    return files[-1] if files else "N/A"


def compare_results(current: dict, previous: dict) -> dict:
    cur_agg = current.get("aggregate", {})
    prev_agg = previous.get("aggregate", {})

    cur_net = cur_agg.get("total_net", 0)
    prev_net = prev_agg.get("total_net", 0)
    improvement_pct = ((cur_net - prev_net) / max(abs(prev_net), 1e-10)) * 100

    cur_pos = cur_agg.get("positive_folds", 0)
    prev_pos = prev_agg.get("positive_folds", 0)

    cur_wf_acc = cur_agg.get("weighted_accuracy", 0)
    prev_wf_acc = prev_agg.get("weighted_accuracy", 0)

    return {
        "previous_net_pnl": round(prev_net, 2),
        "current_net_pnl": round(cur_net, 2),
        "improvement_pct": round(improvement_pct, 1),
        "previous_positive_folds": prev_pos,
        "current_positive_folds": cur_pos,
        "previous_weighted_accuracy": round(prev_wf_acc, 4),
        "current_weighted_accuracy": round(cur_wf_acc, 4),
        "previous_n_folds": prev_agg.get("n_folds", 0),
        "current_n_folds": cur_agg.get("n_folds", 0),
    }


def determine_verdict_from_current(wf_agg: dict, backtest: dict | None) -> tuple[str, str]:
    n_folds = wf_agg.get("n_folds", 1)
    positive_folds = wf_agg.get("positive_folds", 0)
    positive_pct = positive_folds / max(n_folds, 1)
    total_net = wf_agg.get("total_net", 0)
    t_stat = wf_agg.get("net_stability_t", 0.0)

    # NOTE: t_stat assumes fold residuals are independent — in walk-forward
    # with overlapping sliding windows, serial correlation may underestimate
    # SE. Use |t| >= 2 as a flag, not exact p-value, until verified with
    # block-bootstrap or Newey-West SE.
    is_significant = abs(t_stat) >= 2.0

    if positive_pct > 0.6 and total_net > 5:
        return "PASS_TO_NEXT_PHASE", (
            f"Edge is stable: {positive_folds}/{n_folds} folds positive "
            f"({positive_pct:.0%}), net ${total_net:.2f}"
        )

    if is_significant and total_net < 0:
        return "NEGATIVE_EDGE_CONFIRMED", (
            f"t={t_stat:.2f} (|t|>=2), net=${total_net:.2f} over {n_folds} folds. "
            f"Statistically significant LOSS. Do not collect more data — "
            f"fix R:R/exit logic or cost model first."
        )

    if positive_pct > 0.4 and total_net > 0:
        return "CONDITIONAL_PASS", (
            f"Edge is emerging but not yet stable. "
            f"{positive_folds}/{n_folds} folds positive, net=${total_net:.2f}"
        )

    if not is_significant:
        return "INSUFFICIENT_SAMPLE", (
            f"t={t_stat:.2f}, not significant yet. "
            f"Need more folds before concluding."
        )

    return "ARCHIVE_NO_EDGE", (
        f"No positive signal — net=${total_net:.2f}, t={t_stat:.2f}. "
        f"No statistically significant edge found."
    )


def determine_verdict(wf_agg: dict, backtest: dict | None) -> tuple[str, str]:
    return determine_verdict_from_current(wf_agg, backtest)


# ─── Phase 7: Report ──────────────────────────────────────────────────────

def get_verdict_change(prev_verdict: str | None, current_verdict: str) -> str | None:
    if prev_verdict is None:
        return None
    if prev_verdict == current_verdict:
        return None
    return f"{prev_verdict} -> {current_verdict}"


def compute_prev_verdict(previous: dict | None, current_wf_agg: dict) -> str | None:
    if previous is None:
        return None
    prev_agg = previous.get("aggregate", {})
    verdict, _ = determine_verdict(prev_agg, None)
    return verdict


def generate_report(
    symbol: str, timeframe: str, start: str | None, end: str | None,
    df: pd.DataFrame, data_summary: dict,
    wf_result: dict | None, backtest_result: dict | None,
    comparison: dict, previous_result: dict | None,
    wf_dir: str, freq_pd: str,
    verdict: str, recommendation: str,
    elapsed: dict[str, float],
) -> dict:
    wf_agg = wf_result.get("aggregate", {}) if wf_result else {}
    n_folds = wf_agg.get("n_folds", 0)
    positive_folds = wf_agg.get("positive_folds", 0)
    positive_pct = round(positive_folds / max(n_folds, 1) * 100, 1)

    prev_path = format_previous_path(wf_dir, symbol, freq_pd)
    prev_verdict = compute_prev_verdict(previous_result, wf_agg)

    report: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "period": {"start": start or "N/A", "end": end or "N/A"},
        "data_summary": data_summary,
        "walk_forward": {
            "n_folds": n_folds,
            "positive_folds": positive_folds,
            "positive_pct": positive_pct,
            "aggregate_net_pnl": wf_agg.get("total_net", 0),
            "weighted_accuracy": wf_agg.get("weighted_accuracy", 0),
            "net_stability_t": wf_agg.get("net_stability_t", 0),
            "fold_results": wf_result.get("folds", []) if wf_result else [],
        } if wf_result else None,
        "backtest": {
            "net_pnl_with_costs": backtest_result.get("total_cost", 0),
            "win_rate": 0,
            "avg_trade_pnl": 0,
            "max_drawdown_pct": 0,
        } if backtest_result else None,
        "comparison": {
            "previous_run": prev_path,
            "previous_net_pnl": comparison.get("previous_net_pnl", 0),
            "current_net_pnl": comparison.get("current_net_pnl", 0),
            "improvement_pct": comparison.get("improvement_pct", 0),
            "previous_positive_folds": comparison.get("previous_positive_folds", 0),
            "current_positive_folds": comparison.get("current_positive_folds", 0),
        },
        "previous_verdict": prev_verdict,
        "verdict": verdict,
        "recommendation": recommendation,
        "elapsed_seconds": elapsed,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if backtest_result:
        bt_results = backtest_result.get("results", [])
        positive = [r for r in bt_results if isinstance(r, dict) and r.get("net_pnl", 0) > 0 and r.get("n_trades", 0) >= 5]
        best = max(positive, key=lambda r: r["net_pnl"]) if positive else None
        if not best and bt_results:
            best = max(bt_results, key=lambda r: r.get("net_pnl", 0))
        report["backtest"] = {
            "net_pnl_with_costs": round(best["net_pnl"], 2) if best else 0,
            "win_rate": round(best.get("win_rate", 0), 4) if best else 0,
            "accuracy": round(best.get("accuracy", 0), 4) if best else 0,
            "avg_trade_pnl": round(best.get("net_pnl", 0) / max(best.get("n_trades", 1), 1), 2) if best else 0,
            "max_drawdown_pct": round(best.get("max_drawdown", 0), 2) if best else 0,
            "n_trades": best.get("n_trades", 0) if best else 0,
            "sharpe_ratio": round(best.get("sharpe_ratio", 0), 2) if best else 0,
            "total_cost": round(best.get("total_cost", 0), 2) if best else 0,
            "best_confidence_threshold": best.get("min_confidence", 0) if best else 0,
            "oos_raw_accuracy": round(backtest_result.get("oos_raw_accuracy", 0), 4),
            "positive_at_any": backtest_result.get("positive_at_any", False),
        }

    if previous_result:
        report["comparison"]["verdict_change"] = get_verdict_change(prev_verdict, verdict)

    return report


def print_human_summary(report: dict):
    print()
    print("=" * 72)
    print(f"  WALK-FORWARD RE-RUN REPORT — {report['symbol']} @ {report['timeframe']}")
    print("=" * 72)
    feat_count = report['data_summary'].get('features', 'N/A')
    print(f"  Period:     {report['period']['start']} to {report['period']['end']}")
    print(f"  Bars:       {report['data_summary'].get('bars', 'N/A')}")
    if feat_count and feat_count != 'N/A' and feat_count > 0:
        print(f"  Features:   {feat_count}")
    print()

    wf = report.get("walk_forward")
    if wf:
        print("  Walk-Forward:")
        print(f"    Folds:      {wf['n_folds']}  "
              f"Positive: {wf['positive_folds']}/{wf['n_folds']} ({wf['positive_pct']}%)")
        print(f"    Net P&L:    ${wf['aggregate_net_pnl']:>+.2f}")
        print(f"    Wtd Acc:    {wf['weighted_accuracy']:.4f}")
        print(f"    t-stat:     {wf['net_stability_t']:.2f}")
        print()

    bt = report.get("backtest")
    if bt:
        print("  Cost Backtest (best threshold):")
        print(f"    Net P&L:    ${bt['net_pnl_with_costs']:>+.2f}")
        print(f"    Win Rate:   {bt['win_rate']:.1%}")
        print(f"    Accuracy:   {bt.get('accuracy', 0):.1%}")
        print(f"    Sharpe:     {bt.get('sharpe_ratio', 0):.2f}")
        print(f"    Max DD:     {bt['max_drawdown_pct']:.1f}%")
        print(f"    Trades:     {bt.get('n_trades', 0)}")
        print()

    cmp = report.get("comparison", {})
    print("  Comparison with Previous:")
    if cmp.get("previous_run") and cmp["previous_run"] != "N/A":
        prev_label = f"${cmp['previous_net_pnl']:>+.2f}" if cmp.get("previous_net_pnl") != 0 else "N/A"
        print(f"    Previous:   {prev_label} "
              f"({cmp['previous_positive_folds']} folds positive)")
    cur_label = f"${cmp['current_net_pnl']:>+.2f}" if cmp.get("current_net_pnl") != 0 else "N/A"
    print(f"    Current:    {cur_label} "
          f"({cmp['current_positive_folds']} folds positive)")
    if cmp.get("improvement_pct") and cmp["improvement_pct"] != 0:
        print(f"    Change:     {cmp['improvement_pct']:>+.1f}%")
    vc = cmp.get("verdict_change")
    if vc:
        print(f"    Verdict:    {vc}")
    if not cmp.get("previous_run") or cmp["previous_run"] == "N/A":
        print("    (No previous run for comparison)")
    print()

    pv = report.get("previous_verdict")
    if pv:
        print(f"  Previous Verdict: {pv}")
    print(f"  Verdict: {report['verdict']}")
    print(f"  {report['recommendation']}")
    print(f"  Generated: {report['generated_at']}")
    print("=" * 72)
    print()


# ─── Main Pipeline ────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Walk-Forward Re-run Pipeline — from warehouse data to verdict",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_walk_forward.py --symbol EURUSD --timeframe M15
  python scripts/run_walk_forward.py --symbol XAUUSD --quick
  python scripts/run_walk_forward.py --symbol EURUSD --timeframe M15 --verbose
        """,
    )
    parser.add_argument("--symbol", default="EURUSD", help="Trading symbol (default: EURUSD)")
    parser.add_argument("--timeframe", default="M15", help="Timeframe (default: M15)")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="OHLCV data directory")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--features", default="session,regime,microstructure",
        help="Comma-separated feature groups (session,regime,microstructure)",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--db-path", default=None, help="DuckDB database path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    wf_group = parser.add_argument_group("Walk-Forward Parameters")
    wf_group.add_argument("--quick", action="store_true", help="Quick mode (fewer folds)")
    wf_group.add_argument("--train-window", type=int, default=None, help="Training window (bars)")
    wf_group.add_argument("--test-window", type=int, default=None, help="Test window (bars)")
    wf_group.add_argument("--step", type=int, default=None, help="Step size (bars)")
    wf_group.add_argument("--spread-cost", type=float, default=0.024, help="Spread cost per trade ($)")
    wf_group.add_argument("--slippage-p90", type=float, default=0.02, help="Slippage P90 per trade ($)")
    wf_group.add_argument("--cost-config", type=str, default=os.path.join(BASE, "config", "cost_calibration.json"),
        help="Path to cost calibration JSON for symbol-specific costs.")
    wf_group.add_argument("--min-confidence", type=float, default=0.85, help="Minimum confidence threshold")
    wf_group.add_argument("--max-depth", type=int, default=5, help="XGBoost max depth")
    wf_group.add_argument("--n-estimators", type=int, default=100, help="XGBoost n_estimators")

    skip_group = parser.add_argument_group("Skip Flags")
    skip_group.add_argument("--skip-features", action="store_true", help="Skip feature engineering step")
    skip_group.add_argument("--skip-advanced", action="store_true", help="Skip advanced features step")
    skip_group.add_argument("--skip-labels", action="store_true", help="Skip triple-barrier labels step")
    skip_group.add_argument("--skip-backtest", action="store_true", help="Skip cost backtest step")

    return parser.parse_args()


def main():
    args = parse_args()

    symbol = args.symbol
    timeframe = args.timeframe
    freq_pd = FREQ_PD.get(timeframe, timeframe.lower())
    feature_groups = [g.strip() for g in args.features.split(",")]

    train_window = args.train_window or (200 if args.quick else 500)
    test_window = args.test_window or (100 if args.quick else 200)
    step = args.step or (100 if args.quick else 200)

    feat_dir = DEFAULT_FEAT_DIR
    feat_v2_dir = DEFAULT_FEAT_V2_DIR
    label_dir = DEFAULT_LABEL_DIR
    wf_prev_dir = DEFAULT_WF_DIR
    out_dir = args.output_dir
    bt_out_dir = os.path.join(out_dir, "backtest")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(bt_out_dir, exist_ok=True)

    elapsed: dict[str, float] = {}
    pipeline_ok = True

    # ── Header ──
    print()
    print("=" * 72)
    print("  WALK-FORWARD RE-RUN PIPELINE")
    print(f"  {symbol} @ {timeframe}")
    if args.start or args.end:
        print(f"  Period: {args.start or '∞'} to {args.end or '∞'}")
    print(f"  Output: {out_dir}")
    print(f"  WF windows: train={train_window} test={test_window} step={step}")
    print(f"  Cost: ${args.spread_cost+args.slippage_p90:.3f}/trade  Conf>={args.min_confidence}")
    if args.quick:
        print("  Mode: QUICK")
    print("=" * 72)
    print()

    # ── Phase 1: Load Data ──
    print("--- Phase 1: Data Loading ---")
    t_phase = time.time()
    try:
        df = load_ohlcv(
            data_dir=args.data_dir,
            symbol=symbol,
            freq=timeframe,
            start=args.start,
            end=args.end,
            db_path=args.db_path,
        )
    except Exception as e:
        print(f"  [ERROR] Data loading failed: {e}")
        sys.exit(1)

    data_summary: dict[str, Any] = {
        "bars": len(df),
        "date_range": f"{df.index[0]} to {df.index[-1]}",
        "columns": list(df.columns),
        "features": 0,
    }
    elapsed["data_loading"] = round(time.time() - t_phase, 1)
    print(f"  Bars: {len(df)}, Range: {df.index[0]} to {df.index[-1]}")
    print()

    # ── Phase 2: Feature Engineering ──
    print("--- Phase 2: Feature Engineering ---")
    t_phase = time.time()
    if args.skip_features:
        print("  Skipped (--skip-features)")
        features = None
    else:
        features = build_features_pipeline(
            df, symbol, timeframe, freq_pd,
            feat_dir, feat_v2_dir,
            feature_groups,
        )

    if features is not None:
        feat_cols = [c for c in features.columns
                     if c not in ("symbol", "freq", "target", "target_return")]
        data_summary["features"] = len(feat_cols)

    if "microstructure" in feature_groups and not args.skip_advanced:
        print("\n--- Phase 2b: Advanced Features ---")
        adv_ok = run_advanced_features(symbol, freq_pd, feat_dir, feat_v2_dir, args.verbose)
        if not adv_ok:
            print("  Proceeding with basic features only")

    elapsed["feature_engineering"] = round(time.time() - t_phase, 1)
    print()

    # ── Phase 3: Triple-Barrier Labels ──
    print("--- Phase 3: Triple-Barrier Labels ---")
    t_phase = time.time()
    if args.skip_labels:
        print("  Skipped (--skip-labels)")
    else:
        run_triple_barrier_labels(symbol, freq_pd, feat_dir, label_dir, args.verbose)
    elapsed["labeling"] = round(time.time() - t_phase, 1)
    print()

    # ── Phase 4: Walk-Forward ──
    print("--- Phase 4: Walk-Forward Validation ---")
    t_phase = time.time()
    wf_result = run_walk_forward(
        symbol=symbol,
        freq_pd=freq_pd,
        train_window=train_window,
        test_window=test_window,
        step=step,
        spread_cost=args.spread_cost,
        slippage_p90=args.slippage_p90,
        min_confidence=args.min_confidence,
        max_depth=args.max_depth,
        n_estimators=args.n_estimators,
        output_dir=out_dir,
        seed=args.seed,
        verbose=args.verbose,
        cost_config=args.cost_config,
    )
    if wf_result is None:
        print("  [ERROR] Walk-forward produced no result. Cannot continue.")
        pipeline_ok = False
    elapsed["walk_forward"] = round(time.time() - t_phase, 1)
    print()

    # ── Phase 5: Cost Backtest ──
    print("--- Phase 5: Cost Backtest ---")
    t_phase = time.time()
    backtest_result = None
    if not args.skip_backtest:
        backtest_result = run_cost_backtest(
            symbol=symbol,
            freq_pd=freq_pd,
        spread_cost=args.spread_cost,
        slippage_p90=args.slippage_p90,
        output_dir=bt_out_dir,
        verbose=args.verbose,
        cost_config=args.cost_config,
    )
    elapsed["cost_backtest"] = round(time.time() - t_phase, 1)
    print()

    # ── Phase 6: Comparison & Verdict ──
    print("--- Phase 6: Results Comparison & Verdict ---")
    t_phase = time.time()

    previous_result = find_previous_result(wf_prev_dir, symbol, freq_pd)
    if previous_result:
        print(f"  Previous run found: {wf_prev_dir}")
        prev_agg = previous_result.get("aggregate", {})
        print(f"    Net: ${prev_agg.get('total_net', 0):>+.2f}  "
              f"Positive folds: {prev_agg.get('positive_folds', 0)}/{prev_agg.get('n_folds', 0)}")
    else:
        print("  No previous run found")

    comparison: dict[str, Any] = {
        "previous_net_pnl": 0, "current_net_pnl": 0, "improvement_pct": 0,
        "previous_positive_folds": 0, "current_positive_folds": 0,
    }
    if previous_result and wf_result:
        comparison = compare_results(wf_result, previous_result)
        print("  Comparison:")
        print(f"    Previous net: ${comparison['previous_net_pnl']:>+.2f}")
        print(f"    Current net:  ${comparison['current_net_pnl']:>+.2f}")
        print(f"    Improvement:  {comparison['improvement_pct']:>+.1f}%")
    elif wf_result:
        wf_agg = wf_result.get("aggregate", {})
        comparison["current_net_pnl"] = wf_agg.get("total_net", 0)
        comparison["current_positive_folds"] = wf_agg.get("positive_folds", 0)

    if wf_result:
        verdict, recommendation = determine_verdict(
            wf_result.get("aggregate", {}), backtest_result
        )
    else:
        verdict = "INSUFFICIENT_SAMPLE"
        recommendation = "Walk-forward failed to produce results. Check logs."

    elapsed["comparison"] = round(time.time() - t_phase, 1)
    print(f"  Verdict: {verdict}")
    print()

    # ── Phase 7: Report ──
    print("--- Phase 7: Report Generation ---")
    t_phase = time.time()

    report = generate_report(
        symbol=symbol, timeframe=timeframe,
        start=args.start, end=args.end,
        df=df, data_summary=data_summary,
        wf_result=wf_result, backtest_result=backtest_result,
        comparison=comparison, previous_result=previous_result,
        wf_dir=wf_prev_dir, freq_pd=freq_pd,
        verdict=verdict, recommendation=recommendation,
        elapsed=elapsed,
    )

    report_path = os.path.join(out_dir, f"wf_run_{symbol}_{timeframe}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    elapsed["report"] = round(time.time() - t_phase, 1)
    print()

    # ── Human Summary ──
    print_human_summary(report)

    print(f"Pipeline complete. Total time: {sum(elapsed.values()):.1f}s")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
