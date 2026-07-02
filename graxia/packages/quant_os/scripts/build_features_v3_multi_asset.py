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
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from repo root directly
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.macro_features import _shift_series
from core.smc_detectors import (
    classify_killzone,
    detect_fractals,
    detect_fvg,
    detect_judas_swings,
    detect_liquidity_pools,
    detect_liquidity_voids,
    detect_mitigation_and_inversion,
    detect_order_blocks,
    detect_ote,
    detect_structure,
    detect_sweeps,
    detect_wyckoff_events,
    volume_profile_features,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"

# ── Feature deletion/quarantine list ──
DELETION_LIST_PATH = DATA_DIR / "feature_deletion_list.json"


def _load_deletion_list() -> dict[str, str]:
    """Load feature deletion list. Returns {feature_name: action}."""
    if not DELETION_LIST_PATH.exists():
        logger.warning("Feature deletion list not found: %s", DELETION_LIST_PATH)
        return {}
    with open(DELETION_LIST_PATH) as f:
        data = json.load(f)
    return {name: info["action"] for name, info in data.get("features", {}).items()}


_DELETED_FEATURES: set[str] = set()
_QUARANTINED_FEATURES: set[str] = set()


def _init_feature_filters() -> None:
    """Populate deleted/quarantined feature sets from the deletion list."""
    global _DELETED_FEATURES, _QUARANTINED_FEATURES
    actions = _load_deletion_list()
    _DELETED_FEATURES = {k for k, v in actions.items() if v == "DELETE"}
    _QUARANTINED_FEATURES = {k for k, v in actions.items() if v == "QUARANTINE"}
    if _DELETED_FEATURES:
        logger.info("  Deleted features (will be skipped): %s", sorted(_DELETED_FEATURES))
    if _QUARANTINED_FEATURES:
        logger.info("  Quarantined features (flagged): %s", sorted(_QUARANTINED_FEATURES))


OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "features_v3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Macros are shared; COT is gold/silver only, but we include net positioning
# columns for every symbol because they are a global risk proxy.
FRED_DIR = DATA_DIR / "market_data" / "fred"
COT_DIR = DATA_DIR / "market_data" / "cot"

# Core macro series required by the plan
CORE_FRED_SERIES = [
    "DFII10",  # 10Y real yield
    "DGS10",  # 10Y nominal yield
    "VIXCLS",  # equity vol
    "GVZCLS",  # gold vol
    "DCOILWTICO",  # oil
    "DTWEXBGS",  # broad dollar
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
        # Drop columns that are in the deletion list
        cols_to_drop = [c for c in b.columns if c in _DELETED_FEATURES]
        if cols_to_drop:
            logger.info("    Skipping deleted features: %s", cols_to_drop)
            b = b.drop(columns=cols_to_drop)
        # Warn about quarantined features
        quarantined_cols = [c for c in b.columns if c in _QUARANTINED_FEATURES]
        if quarantined_cols:
            logger.warning("    Quarantined features (kept but flagged): %s", quarantined_cols)
        if not b.empty:
            df = pd.concat([df, b.reset_index(drop=True)], axis=1)
    return df


def add_fred_features(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time safe join of daily FRED series onto the intraday index.

    Uses _shift_series with 1-day lag to prevent lookahead: a macro value
    published on day T is only available on day T+1.
    """
    if not FRED_DIR.exists():
        logger.warning("  FRED directory not found, skipping macro features")
        return df

    logger.info("  -> FRED macro features (PIT-safe, 1-day lag)")
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

    # PIT-safe: map to daily dates, then shift by 1 day
    df_date = df["time"].dt.floor("D")
    result_frames = []
    for col in macro.columns:
        day_map = macro[col].dropna()
        mapped = df_date.map(day_map)
        mapped.index = df.index
        # Apply 1-day lag: value published day T available day T+1
        shifted = _shift_series(mapped, 1)
        shifted.name = f"{col}_daily"
        result_frames.append(shifted)

    return pd.concat([df] + result_frames, axis=1)


def add_cot_features(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time safe join of weekly COT positioning onto the intraday index.

    Uses _shift_series with 2-day lag: COT report published Friday is only
    available Monday (T+2 for weekend gap).
    """
    if not COT_DIR.exists():
        logger.warning("  COT directory not found, skipping positioning features")
        return df

    logger.info("  -> COT positioning features (PIT-safe, 2-day lag)")
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
    df_week = df["time"].dt.to_period("W").dt.to_timestamp().dt.tz_localize("UTC")

    result_frames = []
    for col in cols:
        week_map = cot[col].dropna()
        mapped = df_week.map(week_map)
        mapped.index = df.index
        # Apply 2-day lag: COT report Friday -> available Monday
        shifted = _shift_series(mapped, 2)
        shifted.name = f"cot_gold_{col}"
        result_frames.append(shifted)

    return pd.concat([df] + result_frames, axis=1)


def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute standard technical indicators for ML features.

    Indicators (all lag-safe — use only past/current bar data):
    - RSI 14
    - MACD (12, 26, 9) with signal and histogram
    - Bollinger Band width (20, 2σ)
    - ATR ratio (ATR14 / close)
    - ADX (14)
    - Distance from MA 20, 50, 200
    """
    logger.info("  -> Technical features")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --- RSI 14 ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # --- MACD (12, 26, 9) ---
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # --- Bollinger Band width (20, 2σ) ---
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    df["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)

    # --- ATR ratio (ATR14 / close) ---
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    df["atr_ratio"] = atr_14 / close.replace(0, np.nan)

    # --- ADX (14) ---
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr_smooth = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx_14"] = dx.rolling(14).mean()

    # --- Distance from MA 20, 50, 200 ---
    for period in [20, 50, 200]:
        ma = close.rolling(period).mean()
        df[f"dist_ma_{period}"] = (close - ma) / ma.replace(0, np.nan)

    return df


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object/string columns to numeric codes for ML."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype("category").cat.codes.replace(-1, np.nan)
    return df


def build_features(symbol: str, timeframe: str = "M15") -> pd.DataFrame:
    """Build the full features_v3 DataFrame for one symbol."""
    logger.info("Building features_v3 for %s %s", symbol, timeframe)
    _init_feature_filters()
    df = load_ohlcv(symbol, timeframe)
    df = add_smc_features(df)
    df = add_technical_features(df)
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
