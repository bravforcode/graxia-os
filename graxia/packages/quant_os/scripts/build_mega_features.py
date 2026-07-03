#!/usr/bin/env python
"""
Build comprehensive multi-source feature engineering pipeline for XAUUSD.

Data Sources:
  - MT5 M15 OHLCV (base time alignment)
  - yfinance daily (28 tickers)
  - FRED daily/monthly (35 series)
  - COT weekly positioning (gold + silver)

Output: artifacts/features_v3/features_v3_mega_XAUUSD_15min.parquet
"""

import time
import warnings
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ──────────────────────────── PATHS ────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MARKET_DIR = DATA_DIR / "market_data"
YF_DIR = MARKET_DIR / "yfinance"
FRED_DIR = MARKET_DIR / "fred"
COT_DIR = MARKET_DIR / "cot"
OUTPUT_DIR = ROOT / "artifacts" / "features_v3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# SECTION 1: LOAD BASE DATA
# ══════════════════════════════════════════════════════════════

def load_mt5_m15() -> pd.DataFrame:
    """Load XAUUSD M15 as base time index."""
    log("Loading MT5 M15 data...")
    df = pd.read_csv(DATA_DIR / "XAUUSD_M15.csv")
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = df.rename(columns={"time": "datetime"})
    log(f"  MT5 M15: {len(df)} rows, {df.datetime.min()} to {df.datetime.max()}")
    return df


# ══════════════════════════════════════════════════════════════
# SECTION 2: LOAD YFINANCE DAILY DATA
# ══════════════════════════════════════════════════════════════

YF_TICKERS = {
    "GC_F": "gold_futures", "GLD": "gld_etf", "IAU": "iau_etf",
    "SI_F": "silver_futures", "SLV": "slv_etf",
    "CL_F": "crude_oil", "BZ_F": "brent_oil", "NG_F": "nat_gas",
    "DX-Y.NYB": "dxy",
    "_VIX": "vix", "_TNX": "tnx_10y", "_FVX": "fvx_5y", "_TYX": "tyx_30y",
    "TLT": "tlt", "IEF": "ief", "SHY": "shy",
    "_GSPC": "sp500", "_DJI": "djia", "_IXIC": "nasdaq", "_RUT": "russell2000",
    "EURUSD_X": "eurusd", "GBPUSD_X": "gbpusd", "USDJPY_X": "usdjpy",
    "BTC-USD": "btc", "ETH-USD": "eth",
    "DBA": "dbagriculture", "UUP": "uup_dollar", "UDN": "udn_dollar",
}


def load_yfinance_daily() -> pd.DataFrame:
    """Load all yfinance daily CSVs, return wide DataFrame indexed by date."""
    log("Loading yfinance daily data...")
    frames = {}
    for fname, label in YF_TICKERS.items():
        fpath = YF_DIR / f"{fname}.csv"
        if not fpath.exists():
            log(f"  SKIP {fname}: not found")
            continue
        df = pd.read_csv(fpath)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        for col in ["Close", "High", "Low", "Open", "Volume"]:
            if col in df.columns:
                frames[f"{label}_{col.lower()}"] = df[col]
    wide = pd.DataFrame(frames)
    wide.index.name = "date"
    log(f"  yfinance: {len(wide.columns)} series, {len(wide)} days")
    return wide


# ══════════════════════════════════════════════════════════════
# SECTION 3: LOAD FRED DATA
# ══════════════════════════════════════════════════════════════

FRED_DAILY = [
    "DFII10", "DGS10", "DGS2", "DGS30", "DGS5", "DGS7", "DGS3MO", "DGS6MO",
    "T10YIE", "T10Y2Y", "T5YIE", "T5YIFR",
    "GVZCLS", "VIXCLS",
    "DCOILWTICO", "DCOILBRENTEU",
    "DTWEXBGS", "DEXUSEU", "DEXJPUS",
    "BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "BAMLH0A1HYBB",
    "TEDRATE", "BAA10Y",
    "WALCL", "BOGMBASE", "RRPONTSYD", "WTREGEN",
]

FRED_MONTHLY = [
    "UNRATE", "CPIAUCSL", "CPILFESL", "FEDFUNDS", "INDPRO", "UMCSENT",
]


def load_fred_data() -> pd.DataFrame:
    """Load all FRED series, return wide DataFrame indexed by date."""
    log("Loading FRED data...")
    frames = {}
    for sid in FRED_DAILY:
        fpath = FRED_DIR / f"{sid}.csv"
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={"value": f"fred_{sid.lower()}"})
        frames[f"fred_{sid.lower()}"] = df.iloc[:, 0]
    for sid in FRED_MONTHLY:
        fpath = FRED_DIR / f"{sid}.csv"
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={"value": f"fred_{sid.lower()}"})
        frames[f"fred_{sid.lower()}"] = df.iloc[:, 0]
    wide = pd.DataFrame(frames)
    wide.index.name = "date"
    log(f"  FRED: {len(wide.columns)} series, {len(wide)} days")
    return wide


# ══════════════════════════════════════════════════════════════
# SECTION 4: LOAD COT DATA
# ══════════════════════════════════════════════════════════════

def load_cot_data() -> pd.DataFrame:
    """Load gold COT weekly positioning."""
    log("Loading COT data...")
    fpath = COT_DIR / "gold_cot_weekly.parquet"
    if not fpath.exists():
        log("  WARN: gold_cot_weekly.parquet not found")
        return pd.DataFrame()
    df = pd.read_parquet(fpath)
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.set_index("report_date").sort_index()
    df.index.name = "date"
    log(f"  COT: {len(df)} weeks, {df.index.min()} to {df.index.max()}")
    return df


# ══════════════════════════════════════════════════════════════
# SECTION 5: GOLD MICROSTRUCTURE FEATURES (from M15)
# ══════════════════════════════════════════════════════════════

def compute_gold_microstructure(df: pd.DataFrame) -> pd.DataFrame:
    """Compute microstructure features from M15 OHLCV."""
    log("Computing gold microstructure features...")
    out = pd.DataFrame(index=df.index)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    opn = df["open"]
    vol = df["volume"].replace(0, np.nan)

    # ── Returns ──
    for w in [1, 5, 10, 15, 30, 60]:
        out[f"ret_{w}bar"] = close.pct_change(w)

    # ── Volatility ──
    for w in [7, 14, 21]:
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        out[f"atr_{w}"] = tr.rolling(w).mean() / close

    for w in [10, 20, 60]:
        out[f"rvol_{w}"] = close.pct_change().rolling(w).std() * np.sqrt(252 * 24 * 4)

    # ── Momentum ──
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    for w in [7, 14, 21]:
        avg_gain = gain.rolling(w).mean()
        avg_loss = loss.rolling(w).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        out[f"rsi_{w}"] = 100 - (100 / (1 + rs))

    # Stochastic %K, %D
    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    out["stoch_k"] = 100 * (close - low14) / (high14 - low14).replace(0, np.nan)
    out["stoch_d"] = out["stoch_k"].rolling(3).mean()

    # CCI
    tp = (high + low + close) / 3
    tp_sma = tp.rolling(20).mean()
    tp_mad = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    out["cci_20"] = (tp - tp_sma) / (0.015 * tp_mad).replace(0, np.nan)

    # Williams %R
    out["willr_14"] = -100 * (high14 - close) / (high14 - low14).replace(0, np.nan)

    # ── Trend ──
    for w in [5, 10, 20, 50, 100, 200]:
        ema = close.ewm(span=w, adjust=False).mean()
        out[f"ema_{w}_dist"] = (close - ema) / ema

    # SMA cross signals
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    out["sma_20_50_cross"] = (sma20 - sma50) / close

    sma50_long = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    out["sma_50_200_cross"] = (sma50_long - sma200) / close

    # ADX (simplified)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["adx_14"] = dx.rolling(14).mean()

    # ── Bollinger Bands ──
    bb_sma = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_sma + 2 * bb_std
    bb_lower = bb_sma - 2 * bb_std
    out["bb_width"] = (bb_upper - bb_lower) / bb_sma
    out["bb_pctb"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # Squeeze detection: BB width < 0.5 * 20-period avg BB width
    bb_width_avg = out["bb_width"].rolling(120).mean()
    out["bb_squeeze"] = (out["bb_width"] < 0.5 * bb_width_avg).astype(float)

    # ── Volume ──
    # OBV
    obv = (vol * np.sign(close.diff())).fillna(0).cumsum()
    out["obv_slope_20"] = obv.diff(20) / obv.rolling(20).mean().abs().replace(0, np.nan)

    # VWAP (session-based approximation: 24*4=96 bars per day for M15)
    tp_vol = tp * vol
    out["vwap_dist"] = (close - tp_vol.rolling(96).sum() / vol.rolling(96).sum()) / close

    # Volume ratio: current / 20-bar avg
    vol_ma20 = vol.rolling(20).mean()
    out["vol_ratio_20"] = vol / vol_ma20.replace(0, np.nan)

    # ── Candlestick patterns ──
    body = close - opn
    body_abs = body.abs()
    hl_range = (high - low).replace(0, np.nan)
    out["body_ratio"] = body_abs / hl_range
    out["upper_shadow"] = (high - pd.concat([close, opn], axis=1).max(axis=1)) / hl_range
    out["lower_shadow"] = (pd.concat([close, opn], axis=1).min(axis=1) - low) / hl_range

    # Doji: body < 10% of range
    out["is_doji"] = (body_abs < 0.1 * hl_range).astype(float)

    # Hammer: small body, long lower shadow (>2x body), small upper shadow
    out["is_hammer"] = (
        (body_abs < 0.3 * hl_range) &
        (out["lower_shadow"] > 2 * body_abs / hl_range) &
        (out["upper_shadow"] < 0.1)
    ).astype(float)

    # Engulfing
    prev_body = body.shift(1)
    out["is_bull_engulf"] = ((body > 0) & (prev_body < 0) & (body_abs > prev_body.abs())).astype(float)
    out["is_bear_engulf"] = ((body < 0) & (prev_body > 0) & (body_abs > prev_body.abs())).astype(float)

    log(f"  Microstructure: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 6: CROSS-ASSET FEATURES
# ══════════════════════════════════════════════════════════════

def compute_cross_asset_features(yf: pd.DataFrame) -> pd.DataFrame:
    """Compute cross-asset ratios and correlations from yfinance daily data."""
    log("Computing cross-asset features...")
    out = pd.DataFrame(index=yf.index)

    # Gold/Silver ratio
    if "gold_futures_close" in yf.columns and "silver_futures_close" in yf.columns:
        out["gold_silver_ratio"] = yf["gold_futures_close"] / yf["silver_futures_close"]
        out["gold_silver_ratio_pct"] = out["gold_silver_ratio"].pct_change()

    # Gold vs DXY (rolling 20-day correlation)
    if "gold_futures_close" in yf.columns and "dxy_close" in yf.columns:
        g = yf["gold_futures_close"].pct_change()
        d = yf["dxy_close"].pct_change()
        out["gold_dxy_corr_20"] = g.rolling(20).corr(d)
        out["gold_dxy_corr_60"] = g.rolling(60).corr(d)

    # Gold/Oil ratio
    if "gold_futures_close" in yf.columns and "crude_oil_close" in yf.columns:
        out["gold_oil_ratio"] = yf["gold_futures_close"] / yf["crude_oil_close"]
        out["gold_oil_ratio_pct"] = out["gold_oil_ratio"].pct_change()

    # Gold vs VIX
    if "gold_futures_close" in yf.columns and "vix_close" in yf.columns:
        out["gold_vix_corr_20"] = yf["gold_futures_close"].pct_change().rolling(20).corr(
            yf["vix_close"].pct_change()
        )
        out["vix_level"] = yf["vix_close"]

    # Gold vs TLT
    if "gold_futures_close" in yf.columns and "tlt_close" in yf.columns:
        out["gold_tlt_corr_20"] = yf["gold_futures_close"].pct_change().rolling(20).corr(
            yf["tlt_close"].pct_change()
        )

    # Gold vs S&P500
    if "gold_futures_close" in yf.columns and "sp500_close" in yf.columns:
        out["gold_sp500_corr_20"] = yf["gold_futures_close"].pct_change().rolling(20).corr(
            yf["sp500_close"].pct_change()
        )

    # Gold vs USD/JPY
    if "gold_futures_close" in yf.columns and "usdjpy_close" in yf.columns:
        out["gold_usdjpy_corr_20"] = yf["gold_futures_close"].pct_change().rolling(20).corr(
            yf["usdjpy_close"].pct_change()
        )

    # Gold vs Bitcoin
    if "gold_futures_close" in yf.columns and "btc_close" in yf.columns:
        out["gold_btc_corr_20"] = yf["gold_futures_close"].pct_change().rolling(20).corr(
            yf["btc_close"].pct_change()
        )

    log(f"  Cross-asset: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 7: MACRO FEATURES (from FRED)
# ══════════════════════════════════════════════════════════════

def compute_macro_features(fred: pd.DataFrame) -> pd.DataFrame:
    """Compute derived macro features from FRED data."""
    log("Computing macro features...")
    out = pd.DataFrame(index=fred.index)

    # Real yield = DFII10 (10Y TIPS yield) — strongest gold driver
    if "fred_dfii10" in fred.columns:
        out["real_yield_10y"] = fred["fred_dfii10"]
        out["real_yield_10y_chg5d"] = fred["fred_dfii10"].diff(5)
        out["real_yield_10y_chg20d"] = fred["fred_dfii10"].diff(20)

    # Breakeven: T10YIE (inflation expectations)
    if "fred_t10yie" in fred.columns:
        out["breakeven_10y"] = fred["fred_t10yie"]
        out["breakeven_10y_chg5d"] = fred["fred_t10yie"].diff(5)

    # Yield curve: T10Y2Y (recession indicator)
    if "fred_t10y2y" in fred.columns:
        out["yield_curve_10y2y"] = fred["fred_t10y2y"]
        out["yield_curve_10y2y_chg5d"] = fred["fred_t10y2y"].diff(5)

    # Dollar: DTWEXBGS (trade-weighted dollar)
    if "fred_dtwexbgs" in fred.columns:
        out["dollar_trade_weighted"] = fred["fred_dtwexbgs"]
        out["dollar_tw_chg5d"] = fred["fred_dtwexbgs"].pct_change(5)
        out["dollar_tw_chg20d"] = fred["fred_dtwexbgs"].pct_change(20)

    # Credit: HY spread
    if "fred_bamlh0a0hym2" in fred.columns:
        out["hy_spread"] = fred["fred_bamlh0a0hym2"]
        out["hy_spread_chg5d"] = fred["fred_bamlh0a0hym2"].diff(5)
        out["hy_spread_zscore"] = (
            (fred["fred_bamlh0a0hym2"] - fred["fred_bamlh0a0hym2"].rolling(60).mean())
            / fred["fred_bamlh0a0hym2"].rolling(60).std().replace(0, np.nan)
        )

    # Fed balance sheet
    if "fred_walcl" in fred.columns:
        out["fed_balance_sheet"] = fred["fred_walcl"]
        out["fed_bs_chg_20d"] = fred["fred_walcl"].pct_change(20)
        out["fed_bs_chg_60d"] = fred["fred_walcl"].pct_change(60)

    # RRP
    if "fred_rrpontsyd" in fred.columns:
        out["rrp_level"] = fred["fred_rrpontsyd"]
        out["rrp_chg_20d"] = fred["fred_rrpontsyd"].pct_change(20)

    # TED spread
    if "fred_tedrate" in fred.columns:
        out["ted_spread"] = fred["fred_tedrate"]

    # BAA10Y credit
    if "fred_baa10y" in fred.columns:
        out["baa10y_spread"] = fred["fred_baa10y"]

    # Monthly series (already at monthly freq, forward-fill later)
    for col in ["fred_unrate", "fred_cpiaucsl", "fred_fedfunds", "fred_indpro", "fred_umcsent"]:
        if col in fred.columns:
            out[col] = fred[col]

    log(f"  Macro: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 8: COT POSITIONING FEATURES
# ══════════════════════════════════════════════════════════════

def compute_cot_features(cot: pd.DataFrame) -> pd.DataFrame:
    """Compute COT positioning features."""
    log("Computing COT features...")
    if cot.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=cot.index)

    # Core positioning
    for col in [
        "commercials_net_pct", "managed_money_net_pct",
        "managed_money_long_pct", "managed_money_short_pct",
        "managed_money_spread_pct",
        "large_spec_net_pct",
    ]:
        if col in cot.columns:
            out[f"cot_{col}"] = cot[col]

    # Weekly changes
    for col in ["commercials_net_pct", "managed_money_net_pct", "large_spec_net_pct"]:
        if col in cot.columns:
            out[f"cot_{col}_chg1w"] = cot[col].diff(1)
            out[f"cot_{col}_chg4w"] = cot[col].diff(4)

    # OI change
    if "oi_change" in cot.columns:
        out["cot_oi_change"] = cot["oi_change"]

    # Extreme positioning alerts (>80th percentile)
    for col in ["commercials_net_pct", "managed_money_net_pct"]:
        if col in cot.columns:
            pct_rank = cot[col].rolling(52, min_periods=20).rank(pct=True)
            out[f"cot_{col}_extreme_high"] = (pct_rank > 0.8).astype(float)
            out[f"cot_{col}_extreme_low"] = (pct_rank < 0.2).astype(float)

    log(f"  COT: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 9: CROSS-ASSET MOMENTUM
# ══════════════════════════════════════════════════════════════

def compute_cross_asset_momentum(yf: pd.DataFrame) -> pd.DataFrame:
    """Compute momentum features for key cross-asset drivers."""
    log("Computing cross-asset momentum...")
    out = pd.DataFrame(index=yf.index)

    momentum_map = {
        "dxy": "dxy",
        "vix": "vix",
        "tlt": "tlt",
        "crude_oil": "oil",
        "silver_futures": "silver",
        "sp500": "sp500",
        "usdjpy": "usdjpy",
        "btc": "btc",
    }

    for src, label in momentum_map.items():
        col = f"{src}_close"
        if col not in yf.columns:
            continue
        for w in [5, 10, 20]:
            out[f"{label}_mom_{w}d"] = yf[col].pct_change(w)

        # Volatility of this asset
        out[f"{label}_vol_20d"] = yf[col].pct_change().rolling(20).std()

    # Bond term premium proxy (TNX - FVX spread change)
    if "tnx_10y_close" in yf.columns and "fvx_5y_close" in yf.columns:
        out["term_premium_10y5y"] = yf["tnx_10y_close"] - yf["fvx_5y_close"]
        out["term_premium_chg5d"] = out["term_premium_10y5y"].diff(5)

    log(f"  Cross-asset momentum: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 10: REGIME DETECTION
# ══════════════════════════════════════════════════════════════

def compute_regime_features(yf: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    """Compute regime detection features."""
    log("Computing regime features...")
    out = pd.DataFrame(index=yf.index)

    # VIX regime
    if "vix_close" in yf.columns:
        vix = yf["vix_close"]
        out["regime_vix_low"] = (vix < 15).astype(float)
        out["regime_vix_high"] = (vix > 25).astype(float)
        out["regime_vix_extreme"] = (vix > 35).astype(float)

    # Yield curve regime
    if "fred_t10y2y" in fred.columns:
        yc = fred["fred_t10y2y"].reindex(yf.index, method="ffill")
        out["regime_yieldcurve_inverted"] = (yc < 0).astype(float)
        out["regime_yieldcurve_flat"] = ((yc >= 0) & (yc < 0.5)).astype(float)

    # Dollar regime
    if "dxy_close" in yf.columns:
        dxy = yf["dxy_close"]
        dxy_ma20 = dxy.rolling(20).mean()
        dxy_ma60 = dxy.rolling(60).mean()
        out["regime_dollar_strong"] = ((dxy > dxy_ma20) & (dxy_ma20 > dxy_ma60)).astype(float)
        out["regime_dollar_weak"] = ((dxy < dxy_ma20) & (dxy_ma20 < dxy_ma60)).astype(float)

    # Credit regime
    if "fred_bamlh0a0hym2" in fred.columns:
        hy = fred["fred_bamlh0a0hym2"].reindex(yf.index, method="ffill")
        hy_p75 = hy.rolling(252, min_periods=60).quantile(0.75)
        out["regime_credit_stressed"] = (hy > hy_p75).astype(float)

    # Gold trend regime
    if "gold_futures_close" in yf.columns:
        g = yf["gold_futures_close"]
        g_ma20 = g.rolling(20).mean()
        g_ma60 = g.rolling(60).mean()
        out["regime_gold_bull"] = ((g > g_ma20) & (g_ma20 > g_ma60)).astype(float)
        out["regime_gold_bear"] = ((g < g_ma20) & (g_ma20 < g_ma60)).astype(float)

    log(f"  Regime: {len(out.columns)} features")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 11: FORWARD-FILL & MERGE
# ══════════════════════════════════════════════════════════════

def align_daily_to_m15(base: pd.DataFrame, daily_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Forward-fill daily features to M15 base time index."""
    log("Forward-filling daily features to M15...")
    base_date = base["datetime"].dt.date
    result = base[["datetime"]].copy()
    result["date"] = pd.to_datetime(base_date)

    for name, ddf in daily_frames.items():
        if ddf.empty:
            continue
        # Normalize index to date
        ddf_idx = ddf.index.normalize()
        ddf.index = ddf_idx
        # Merge on date, then forward-fill
        merged = result[["date"]].merge(
            ddf, left_on="date", right_index=True, how="left"
        )
        merged = merged.set_index(result.index)
        merged = merged.drop(columns=["date"], errors="ignore")
        merged = merged.ffill()
        for col in merged.columns:
            result[col] = merged[col]

    log(f"  After merge: {len(result.columns)} columns")
    return result


# ══════════════════════════════════════════════════════════════
# SECTION 12: TARGETS
# ══════════════════════════════════════════════════════════════

def compute_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Create forward return targets."""
    log("Computing targets...")
    close = df["close"]

    # Forward returns
    for w in [1, 5, 10, 15]:
        df[f"fwd_ret_{w}bar"] = close.shift(-w) / close - 1

    # Binary target
    df["is_long"] = (df["fwd_ret_1bar"] > 0).astype(float)

    # Multi-class: strong up / up / flat / down / strong down
    ret1 = df["fwd_ret_1bar"]
    q33 = ret1.quantile(0.33)
    q66 = ret1.quantile(0.66)
    df["target_class"] = np.where(
        ret1 > q66, 2, np.where(ret1 > 0, 1, np.where(ret1 > q33, 0, -1))
    )

    log("  Targets: fwd_ret_1bar, fwd_ret_5bar, fwd_ret_10bar, fwd_ret_15bar, is_long, target_class")
    return df


# ══════════════════════════════════════════════════════════════
# SECTION 13: FEATURE IMPORTANCE REPORT
# ══════════════════════════════════════════════════════════════

def feature_importance_report(df: pd.DataFrame, top_n: int = 50):
    """Print top features by correlation with target."""
    log("Computing feature importance...")
    target = "fwd_ret_1bar"
    if target not in df.columns:
        return

    feature_cols = [c for c in df.columns if c not in [
        "datetime", "date", "open", "high", "low", "close", "volume",
        "fwd_ret_1bar", "fwd_ret_5bar", "fwd_ret_10bar", "fwd_ret_15bar",
        "is_long", "target_class"
    ]]

    corrs = {}
    for col in feature_cols:
        valid = df[[col, target]].dropna()
        if len(valid) < 100:
            continue
        c = valid[col].corr(valid[target])
        if np.isfinite(c):
            corrs[col] = c

    ranked = sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True)

    print("\n" + "=" * 70)
    print(f"TOP {top_n} FEATURES BY |CORRELATION| with fwd_ret_1bar")
    print("=" * 70)
    print(f"{'Rank':<6}{'Feature':<45}{'Corr':>8}{'|Corr|':>8}")
    print("-" * 70)
    for i, (feat, corr) in enumerate(ranked[:top_n], 1):
        print(f"{i:<6}{feat:<45}{corr:>8.4f}{abs(corr):>8.4f}")
    print("=" * 70)


# ══════════════════════════════════════════════════════════════
# SECTION 14: MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("XAUUSD MEGA FEATURE ENGINEERING PIPELINE v3")
    print("=" * 70)

    # 1. Load base M15
    base = load_mt5_m15()

    # 2. Load all data sources
    yf_wide = load_yfinance_daily()
    fred_wide = load_fred_data()
    cot_df = load_cot_data()

    # 3. Compute gold microstructure (on M15 directly)
    micro = compute_gold_microstructure(base)

    # 4. Compute cross-asset features (daily)
    cross_asset = compute_cross_asset_features(yf_wide)

    # 5. Compute macro features (daily)
    macro = compute_macro_features(fred_wide)

    # 6. Compute COT features (weekly)
    cot_feat = compute_cot_features(cot_df)

    # 7. Compute cross-asset momentum (daily)
    xmomentum = compute_cross_asset_momentum(yf_wide)

    # 8. Compute regime features (daily)
    regime = compute_regime_features(yf_wide, fred_wide)

    # 9. Forward-fill daily/weekly features to M15
    daily_frames = {
        "cross_asset": cross_asset,
        "macro": macro,
        "cot": cot_feat,
        "xmomentum": xmomentum,
        "regime": regime,
    }
    filled = align_daily_to_m15(base, daily_frames)

    # 10. Merge everything
    log("Merging all features...")
    result = base[["datetime"]].copy()
    result["open"] = base["open"]
    result["high"] = base["high"]
    result["low"] = base["low"]
    result["close"] = base["close"]
    result["volume"] = base["volume"]

    # Add micro features (already M15 aligned)
    for col in micro.columns:
        result[col] = micro[col].values

    # Add daily features (already forward-filled)
    for col in filled.columns:
        if col not in ["datetime", "date"]:
            result[col] = filled[col].values

    # 11. Add calendar features
    log("Adding calendar features...")
    dt = result["datetime"]
    result["hour"] = dt.dt.hour
    result["day_of_week"] = dt.dt.dayofweek
    result["day_of_month"] = dt.dt.day
    result["month"] = dt.dt.month
    result["is_london_session"] = ((dt.dt.hour >= 7) & (dt.dt.hour < 16)).astype(float)
    result["is_ny_session"] = ((dt.dt.hour >= 12) & (dt.dt.hour < 21)).astype(float)
    result["is_asian_session"] = ((dt.dt.hour >= 0) & (dt.dt.hour < 7)).astype(float)

    # 12. Compute targets
    result = compute_targets(result)

    # 13. Report
    total_features = len(result.columns) - 7  # exclude datetime + OHLCV + targets
    nan_pct = result.isna().mean().mean() * 100

    # Critical features NaN check
    critical = ["rsi_14", "atr_14", "adx_14", "bb_pctb", "fwd_ret_1bar"]
    crit_nan = {c: result[c].isna().mean() * 100 for c in critical if c in result.columns}

    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)
    print(f"  Total rows:          {len(result):,}")
    print(f"  Total columns:       {len(result.columns)}")
    print(f"  Features (excl OHLCV+target): {total_features}")
    print(f"  Date range:          {result.datetime.min()} to {result.datetime.max()}")
    print(f"  Overall NaN%:        {nan_pct:.1f}%")
    print()
    print("  Critical feature NaN%:")
    for c, n in crit_nan.items():
        print(f"    {c:<20}: {n:.1f}%")

    # Feature category counts
    micro_cols = [c for c in result.columns if any(c.startswith(p) for p in [
        "ret_", "atr_", "rvol_", "rsi_", "stoch_", "cci_", "willr_",
        "ema_", "sma_", "adx_", "bb_", "obv_", "vwap_", "vol_ratio_",
        "body_", "upper_", "lower_", "is_doji", "is_hammer", "is_bull", "is_bear"
    ])]
    xasset_cols = [c for c in result.columns if "gold_silver" in c or "gold_dxy" in c
                    or "gold_oil" in c or "gold_vix" in c or "gold_tlt" in c
                    or "gold_sp500" in c or "gold_usdjpy" in c or "gold_btc" in c]
    macro_cols = [c for c in result.columns if c.startswith("fred_") or c.startswith("regime_yield")]
    cot_cols = [c for c in result.columns if c.startswith("cot_")]
    momentum_cols = [c for c in result.columns if any(c.startswith(p) for p in [
        "dxy_mom", "vix_mom", "tlt_mom", "oil_mom", "silver_mom", "sp500_mom",
        "usdjpy_mom", "btc_mom", "term_premium"
    ])]
    regime_cols = [c for c in result.columns if c.startswith("regime_")]

    print()
    print("  Feature categories:")
    print(f"    Gold microstructure: {len(micro_cols)}")
    print(f"    Cross-asset ratios:  {len(xasset_cols)}")
    print(f"    Macro (FRED):        {len(macro_cols)}")
    print(f"    COT positioning:     {len(cot_cols)}")
    print(f"    Cross-asset momentum:{len(momentum_cols)}")
    print(f"    Regime detection:    {len(regime_cols)}")

    # Feature importance
    feature_importance_report(result, top_n=50)

    # 14. Save
    output_path = OUTPUT_DIR / "features_v3_mega_XAUUSD_15min.parquet"
    result.to_parquet(output_path, index=False)
    log(f"\nSaved to: {output_path}")
    log(f"File size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
    log(f"Total time: {time.time() - t0:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
