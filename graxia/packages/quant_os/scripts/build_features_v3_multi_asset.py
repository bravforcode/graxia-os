"""Build features_v3 for the multi-asset redesign.

Usage:
    python scripts/build_features_v3_multi_asset.py --symbol XAUUSD
    python scripts/build_features_v3_multi_asset.py --symbol EURUSD
    python scripts/build_features_v3_multi_asset.py --symbol BTCUSD
    python scripts/build_features_v3_multi_asset.py --symbol ETHUSD

This is the Phase 3 implementation of MULTI_ASSET_REDESIGN_PLAN_v3.md:
- SMC feature block from core/smc_detectors
- Killzone labels
- Cross-asset macro features (FRED, COT) joined by timestamp
- Outputs one parquet per symbol under artifacts/features_v3/

Lookahead safety: every SMC detector is lag-safe by design. Macro features are
daily/weekly and are forward-filled only up to the current bar.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Allow running from repo root directly
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.smc_detectors import (
    classify_killzone,
    detect_fvg,
    detect_fractals,
    detect_judas_swings,
    detect_liquidity_pools,
    detect_liquidity_voids,
    detect_mitigation_and_inversion,
    detect_order_blocks,
    detect_structure,
    detect_sweeps,
    detect_wyckoff_events,
    detect_ote,
    volume_profile_features,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "features_v3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Macros are shared; COT is gold/silver only, but we include net positioning
# columns for every symbol because they are a global risk proxy.
FRED_DIR = DATA_DIR / "market_data" / "fred"
COT_DIR = DATA_DIR / "market_data" / "cot"

# Core macro series required by the plan
CORE_FRED_SERIES = [
    "DFII10",  # 10Y real yield
    "DGS10",   # 10Y nominal yield
    "VIXCLS",  # equity vol
    "GVZCLS",  # gold vol
    "DCOILWTICO",  # oil
    "DTWEXBGS",    # broad dollar
]


def load_ohlcv(symbol: str, timeframe: str = "M15") -> pd.DataFrame:
    """Load OHLCV CSV and ensure a proper DatetimeIndex."""
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"OHLCV file not found: {path}")
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_smc_features(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full SMC detector block and join feature columns."""
    logger.info("  -> SMC detectors")
    fractals = detect_fractals(df, k=2)
    sweeps = detect_sweeps(df, fractals, sweep_max_atr=0.5, max_reclaim_bars=3)
    obs = detect_order_blocks(df, fractals, impulse_min_atr=1.0, max_lookback_bars=5, max_age_bars=100)
    fvgs = detect_fvg(df, max_age_bars=100)
    structure = detect_structure(df, fractals)
    pools = detect_liquidity_pools(df, fractals, tolerance_atr=0.3, lookback_bars=30, max_age_bars=100)
    killzones = classify_killzone(df["time"])
    ote = detect_ote(df, fractals)
    voids = detect_liquidity_voids(df, lookback=5, min_void_size_atr=1.5)
    mit_inv = detect_mitigation_and_inversion(df, obs.attrs["events"], fvgs.attrs["events"], max_age_bars=100)
    judas = detect_judas_swings(df, sweeps, killzones)
    wyck = detect_wyckoff_events(df, lookback=20, spring_threshold_atr=0.5)
    vp = volume_profile_features(df, lookback=20)

    blocks = [
        fractals[["swing_high", "swing_low"]],
        sweeps[["sweep_bearish_flag", "sweep_bullish_flag", "sweep_magnitude", "bars_since_sweep"]],
        obs[["ob_distance_atr", "ob_age_bars", "ob_strength"]],
        fvgs[["fvg_nearest_distance_atr", "fvg_nearest_size_atr", "fvg_inside_flag"]],
        structure[["structure_state", "bars_since_bos_choch", "structure_event_flag"]],
        pools[["pool_nearest_distance_atr", "pool_age_bars", "pool_strength"]],
        killzones[["is_london_open", "is_ny_open", "is_overlap", "is_crypto_funding"]],
        ote[["ote_in_band", "ote_retracement_pct"]],
        voids[["liquidity_void_flag", "liquidity_void_size_atr", "liquidity_void_age_bars"]],
        mit_inv[["ob_mitigation_depth", "inversion_fvg_flag"]],
        judas[["judas_swing_flag", "judas_direction"]],
        wyck[["wyckoff_range_bound", "wyckoff_spring_flag", "wyckoff_upthrust_flag"]],
        vp[["vp_poc_distance_atr", "vp_inside_value_area", "vp_hvn_proximity"]],
    ]

    for b in blocks:
        df = pd.concat([df, b.reset_index(drop=True)], axis=1)
    return df


def add_fred_features(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill daily FRED series onto the intraday index."""
    if not FRED_DIR.exists():
        logger.warning("  FRED directory not found, skipping macro features")
        return df

    logger.info("  -> FRED macro features")
    macro_frames = []
    for sid in CORE_FRED_SERIES:
        fpath = FRED_DIR / f"{sid}.csv"
        if not fpath.exists():
            logger.warning("    FRED series missing: %s", sid)
            continue
        s = pd.read_csv(fpath, parse_dates=["date"])
        s = s.sort_values("date").set_index("date")["value"]
        s = s.replace(".", np.nan).astype(float)
        s.name = f"fred_{sid.lower()}"
        macro_frames.append(s)

    if not macro_frames:
        return df

    macro = pd.concat(macro_frames, axis=1)
    macro.index = pd.to_datetime(macro.index, utc=True)
    macro = macro.sort_index()

    # Reindex to df dates using forward fill only (no future leak)
    df_date = df["time"].dt.floor("D").rename("date")
    macro_daily = macro.reindex(df_date, method="ffill")
    macro_daily.index = df.index
    return pd.concat([df, macro_daily.add_suffix("_daily")], axis=1)


def add_cot_features(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill weekly COT positioning onto the intraday index."""
    if not COT_DIR.exists():
        logger.warning("  COT directory not found, skipping positioning features")
        return df

    logger.info("  -> COT positioning features")
    cot_path = COT_DIR / "gold_cot_weekly.parquet"
    if not cot_path.exists():
        logger.warning("    COT gold file missing")
        return df

    cot = pd.read_parquet(cot_path)
    cot["report_date"] = pd.to_datetime(cot["report_date"], utc=True)
    cot = cot.sort_values("report_date").set_index("report_date")

    cols = [c for c in ["commercials_net_pct", "managed_money_net_pct", "open_interest"] if c in cot.columns]
    if not cols:
        return df

    cot = cot[cols]
    cot.index = cot.index.tz_localize("UTC") if cot.index.tz is None else cot.index.tz_convert("UTC")
    df_week = df["time"].dt.to_period("W").dt.to_timestamp().dt.tz_localize("UTC").rename("week")
    cot_weekly = cot.reindex(df_week, method="ffill")
    cot_weekly.index = df.index
    cot_weekly = cot_weekly.add_prefix("cot_gold_")
    return pd.concat([df, cot_weekly], axis=1)


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object/string columns to numeric codes for ML."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype("category").cat.codes.replace(-1, np.nan)
    return df


def build_features(symbol: str, timeframe: str = "M15") -> pd.DataFrame:
    """Build the full features_v3 DataFrame for one symbol."""
    logger.info("Building features_v3 for %s %s", symbol, timeframe)
    df = load_ohlcv(symbol, timeframe)
    df = add_smc_features(df)
    df = add_fred_features(df)
    df = add_cot_features(df)
    df = encode_categoricals(df)
    return df


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build features_v3 for multi-asset redesign")
    parser.add_argument("--symbol", required=True, help="XAUUSD, EURUSD, BTCUSD, ETHUSD")
    parser.add_argument("--timeframe", default="M15", help="Base timeframe (default M15)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Output directory")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_features(args.symbol, args.timeframe)
    out_path = out_dir / f"features_v3_{args.symbol}_{args.timeframe}.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Saved %d rows x %d cols to %s", len(df), len(df.columns), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
