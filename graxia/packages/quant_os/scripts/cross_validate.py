"""
Cross-Source Data Validator — Compare price data across multiple sources.

Reads tick/OHLCV data from two or more sources (e.g. MT5, Dukascopy, TrueFX),
resamples to 1-minute bars, and runs five validation checks:

    1. Price Level Comparison — OHLC tolerance
    2. Spread Comparison — expected spread relation
    3. Tick Density Comparison — ticks/min patterns
    4. Gap Detection — shared vs source-only gaps
    5. Correlation Analysis — Pearson r of 1m returns

Usage:
    python scripts/cross_validate.py
        --primary data/warehouse/ticks/source=MT5/
        --secondary data/warehouse/ticks/source=Dukascopy/
        --symbols EURUSD,GBPUSD,XAUUSD
        --start 2024-01-01
        --end 2024-01-31
        --output artifacts/validation/cross_source/
        --tolerance 0.0001
        --correlation-threshold 0.95
"""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "artifacts", "validation", "cross_source")

ALLOWED_EXTENSIONS = {".parquet", ".csv"}
CHECK_NAMES = ["price_alignment", "spread_comparison", "tick_density", "correlation", "gaps"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _discover_files(data_dir: str, symbols: List[str]) -> Dict[str, List[str]]:
    """Map symbol -> list of parquet/csv file paths under *data_dir*.

    Scans all subdirectories (respecting Hive-style partitioning like
    ``source=MT5/year=2024/month=01/data.parquet``) so the caller can pass a
    top-level *source* directory.
    """
    result: Dict[str, List[str]] = {s: [] for s in symbols}
    if not os.path.isdir(data_dir):
        return result

    for ext in ALLOWED_EXTENSIONS:
        for fp in glob(os.path.join(data_dir, "**", f"*{ext}"), recursive=True):
            fp = fp.replace("\\", "/")
            base = os.path.splitext(os.path.basename(fp))[0].upper()
            for sym in symbols:
                if sym.upper() in base:
                    result[sym].append(fp)
                    break
                parts = fp.replace("\\", "/").split("/")
                if sym.upper() in [p.upper() for p in parts]:
                    result[sym].append(fp)
                    break
    return result


def _load_data(file_paths: List[str]) -> pd.DataFrame:
    """Load and concatenate parquet/CSV files into a single DataFrame.

    Returns a DataFrame with at minimum columns needed for resampling
    (timestamp, bid, ask).  If ``time`` is present it is renamed to
    ``timestamp`` for consistency.
    """
    frames = []
    for fp in sorted(file_paths):
        if fp.endswith(".parquet"):
            df = pd.read_parquet(fp)
        elif fp.endswith(".csv"):
            df = pd.read_csv(fp)
        else:
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Normalise timestamp column
    ts_cols = [c for c in df.columns if c.lower() in ("timestamp", "time", "datetime")]
    if not ts_cols:
        return pd.DataFrame()
    ts_col = ts_cols[0]
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df = df.drop(columns=[c for c in ts_cols if c != "timestamp" and c in df.columns],
                 errors="ignore")

    # Ensure numeric bid/ask
    for col in ("bid", "ask"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _resample_ohlcv(df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Resample tick data to OHLCV bars at *freq* using mid prices.

    Uses the midpoint ``(bid + ask) / 2`` when both are available, otherwise
    falls back to whichever price column exists.
    """
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("timestamp").sort_index()

    if "bid" in df.columns and "ask" in df.columns:
        price_col = (df["bid"] + df["ask"]) / 2.0
    elif "bid" in df.columns:
        price_col = df["bid"]
    elif "ask" in df.columns:
        price_col = df["ask"]
    elif "close" in df.columns:
        price_col = df["close"]
    else:
        return pd.DataFrame()

    ohlcv = price_col.resample(freq).ohlc()
    ohlcv.columns = ["open", "high", "low", "close"]

    # Volume
    vol_col = [c for c in df.columns if c.lower() in ("volume", "volume_real", "tick_volume")]
    if vol_col:
        ohlcv["volume"] = df[vol_col[0]].resample(freq).sum()
    else:
        ohlcv["volume"] = price_col.resample(freq).count()

    # Spread
    if "bid" in df.columns and "ask" in df.columns:
        spread = (df["ask"] - df["bid"]).resample(freq).mean()
        ohlcv["spread"] = spread
        ohlcv["spread_points"] = (spread * 10000).round(1)

    # Tick count
    ohlcv["tick_count"] = price_col.resample(freq).count()

    return ohlcv


def _mid_price(df: pd.DataFrame) -> Optional[pd.Series]:
    """Return mid-price series aligned on timestamp index."""
    if df.empty:
        return None
    idx = df.set_index("timestamp").sort_index()
    if "bid" in idx.columns and "ask" in idx.columns:
        return (idx["bid"] + idx["ask"]) / 2.0
    if "close" in idx.columns:
        return idx["close"]
    if "bid" in idx.columns:
        return idx["bid"]
    if "ask" in idx.columns:
        return idx["ask"]
    return None


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def _status(value: float, threshold: float, higher_is_worse: bool = True) -> str:
    """Return PASS / WARN / FAIL given a value and threshold."""
    if math.isnan(value):
        return "FAIL"
    exceeds = value > threshold if higher_is_worse else value < threshold
    if exceeds:
        return "FAIL" if abs(value - threshold) / max(abs(threshold), 1e-12) > 2 else "WARN"
    return "PASS"


def check_price_alignment(
    primary: pd.DataFrame, secondary: pd.DataFrame, tolerance: float
) -> Dict[str, Any]:
    """Compare OHLC values between two resampled sources.

    Tolerance is expressed as a fraction of price (e.g. 0.0001 = 0.01%).
    Open/close use *tolerance*, high/low use ``2 * tolerance``.
    """
    if primary.empty or secondary.empty:
        return {"status": "SKIP", "reason": "One or both sources have no data"}

    aligned = primary.join(secondary, how="inner", lsuffix="_p", rsuffix="_s")
    if aligned.empty:
        return {"status": "SKIP", "reason": "No overlapping timestamps"}

    max_div = 0.0
    details = {}
    for col in ["open", "high", "low", "close"]:
        p_col = f"{col}_p"
        s_col = f"{col}_s"
        if p_col not in aligned.columns or s_col not in aligned.columns:
            continue
        p_vals = aligned[p_col].fillna(0)
        s_vals = aligned[s_col].fillna(0)
        denom = p_vals.abs().replace(0, float("nan"))
        div_pct = ((s_vals - p_vals).abs() / denom * 100).dropna()
        if div_pct.empty:
            details[col] = {"max_divergence_pct": 0, "status": "SKIP"}
            continue
        cd = float(div_pct.max())
        max_div = max(max_div, cd)
        threshold = tolerance * 100 * (2 if col in ("high", "low") else 1)
        details[col] = {
            "max_divergence_pct": round(cd, 4),
            "threshold_pct": round(threshold, 4),
            "over_threshold_count": int((div_pct > threshold).sum()),
        }

    overall_stat = _status(max_div, tolerance * 100)
    return {
        "status": overall_stat,
        "max_divergence_pct": round(max_div, 4),
        "threshold_pct": round(tolerance * 100, 4),
        "details": details,
    }


def check_spread_comparison(
    primary: pd.DataFrame, secondary: pd.DataFrame
) -> Dict[str, Any]:
    """Compare mean spread per hour session.

    Expects Dukascopy (secondary) spreads <= MT5 (primary) spreads.
    """
    if primary.empty or secondary.empty:
        return {"status": "SKIP", "reason": "One or both sources have no data"}

    def _hourly_spreads(df: pd.DataFrame) -> pd.DataFrame:
        if "spread" not in df.columns or df["spread"].isna().all():
            return pd.Series(dtype=float)
        return df["spread"].resample("1h").mean()

    p_spread = _hourly_spreads(primary)
    s_spread = _hourly_spreads(secondary)
    if p_spread.empty or s_spread.empty:
        return {"status": "SKIP", "reason": "Spread data unavailable"}

    aligned = pd.DataFrame({"primary": p_spread, "secondary": s_spread}).dropna()
    if aligned.empty:
        return {"status": "SKIP", "reason": "No overlapping hours for spread comparison"}

    p_mean = float(aligned["primary"].mean())
    s_mean = float(aligned["secondary"].mean())
    violations = int((aligned["primary"] < aligned["secondary"]).sum())
    total = len(aligned)
    violation_pct = violations / total if total > 0 else 0

    if violation_pct > 0.1:
        status = "WARN"
    elif violation_pct > 0.3:
        status = "FAIL"
    else:
        status = "PASS"

    return {
        "status": status,
        "primary_mean_spread": round(p_mean, 5),
        "secondary_mean_spread": round(s_mean, 5),
        "expected_relation": "secondary <= primary",
        "violations_secondary_gt_primary": violations,
        "total_hours": total,
        "violation_pct": round(violation_pct, 4),
    }


def check_tick_density(
    primary: pd.DataFrame, secondary: pd.DataFrame
) -> Dict[str, Any]:
    """Compare ticks-per-minute density between sources."""
    if primary.empty or secondary.empty:
        return {"status": "SKIP", "reason": "One or both sources have no data"}

    def _density(df: pd.DataFrame) -> pd.Series:
        if "tick_count" in df.columns:
            return df["tick_count"].dropna()
        return pd.Series(dtype=float)

    p_den = _density(primary)
    s_den = _density(secondary)
    if p_den.empty or s_den.empty:
        return {"status": "SKIP", "reason": "Tick count data unavailable"}

    aligned = pd.DataFrame({"primary": p_den, "secondary": s_den}).dropna()
    if aligned.empty:
        return {"status": "SKIP", "reason": "No overlapping periods"}

    p_avg = float(aligned["primary"].mean())
    s_avg = float(aligned["secondary"].mean())
    ratio = p_avg / s_avg if s_avg > 0 else float("inf")

    min_ratio = min(p_avg, s_avg) / max(p_avg, s_avg) if max(p_avg, s_avg) > 0 else 1.0

    if min_ratio < 0.25:
        status = "FAIL"
    elif min_ratio < 0.5:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "primary_ticks_per_min_avg": round(p_avg, 2),
        "secondary_ticks_per_min_avg": round(s_avg, 2),
        "ratio_primary_to_secondary": round(ratio, 4),
        "min_ratio": round(min_ratio, 4),
    }


def check_correlation(
    primary: pd.DataFrame, secondary: pd.DataFrame, threshold: float
) -> Dict[str, Any]:
    """Pearson correlation of 1-minute log returns between sources."""
    if primary.empty or secondary.empty:
        return {"status": "SKIP", "reason": "One or both sources have no data"}

    def _returns(df: pd.DataFrame) -> pd.Series:
        if "close" not in df.columns:
            return pd.Series(dtype=float)
        close = df["close"].dropna()
        if len(close) < 2:
            return pd.Series(dtype=float)
        return np.log(close / close.shift(1)).dropna()

    p_ret = _returns(primary)
    s_ret = _returns(secondary)
    if p_ret.empty or s_ret.empty:
        return {"status": "SKIP", "reason": "Insufficient data for return calculation"}

    aligned = pd.DataFrame({"primary": p_ret, "secondary": s_ret}).dropna()
    if len(aligned) < 10:
        return {"status": "SKIP", "reason": f"Fewer than 10 aligned return pairs ({len(aligned)})"}

    r = float(aligned["primary"].corr(aligned["secondary"]))
    if math.isnan(r):
        return {"status": "SKIP", "reason": "Correlation is NaN (constant series)"}

    if r < threshold * 0.9:
        status = "FAIL"
    elif r < threshold:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "pearson_r": round(r, 4),
        "threshold": threshold,
        "aligned_periods": len(aligned),
    }


def check_gaps(
    primary: pd.DataFrame, secondary: pd.DataFrame, gap_threshold_minutes: int = 30
) -> Dict[str, Any]:
    """Detect missing-period gaps and compare across sources.

    A gap is defined as a period where no resampled bar exists for longer than
    *gap_threshold_minutes*.  Gaps present in both sources are likely market
    closes / weekends; gaps in only one source suggest a data-collection issue.
    """
    if primary.empty or secondary.empty:
        return {"status": "SKIP", "reason": "One or both sources have no data"}

    def _find_gaps(df: pd.DataFrame) -> List[Tuple]:
        """Return list of (from_ts, to_ts, gap_minutes) tuples."""
        if df.empty or len(df) < 2:
            return []
        gaps = []
        ts = df.index.sort_values()
        for i in range(1, len(ts)):
            gap_min = (ts[i] - ts[i - 1]).total_seconds() / 60.0
            if gap_min > gap_threshold_minutes:
                gaps.append((ts[i - 1], ts[i], round(gap_min, 1)))
        return gaps

    p_gaps = _find_gaps(primary)
    s_gaps = _find_gaps(secondary)

    # Classify shared vs source-only gaps (within 5-minute tolerance)
    p_only = 0
    s_only = 0
    shared = 0
    for g in p_gaps:
        matched = any(
            abs((g[0] - sg[0]).total_seconds()) < 300
            and abs((g[1] - sg[1]).total_seconds()) < 300
            for sg in s_gaps
        )
        if matched:
            shared += 1
        else:
            p_only += 1

    s_matched = 0
    for sg in s_gaps:
        matched = any(
            abs((sg[0] - pg[0]).total_seconds()) < 300
            and abs((sg[1] - pg[1]).total_seconds()) < 300
            for pg in p_gaps
        )
        if matched:
            s_matched += 1
        else:
            s_only += 1

    total = shared + p_only + s_only
    anomaly_frac = (p_only + s_only) / max(total, 1)

    if anomaly_frac > 0.5:
        status = "FAIL"
    elif anomaly_frac > 0.2:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "shared_gaps": shared,
        "primary_only_gaps": p_only,
        "secondary_only_gaps": s_only,
        "anomaly_frac": round(anomaly_frac, 4),
        "gap_threshold_minutes": gap_threshold_minutes,
    }


# ---------------------------------------------------------------------------
# Per-symbol runner
# ---------------------------------------------------------------------------

def validate_symbol(
    symbol: str,
    primary_dir: str,
    secondary_dir: str,
    start: str,
    end: str,
    tolerance: float,
    corr_threshold: float,
) -> Dict[str, Any]:
    """Run all checks for a single symbol and return the report block."""
    result: Dict[str, Any] = {
        "symbol": symbol,
        "period": {"start": start, "end": end},
        "sources": {},
        "checks": {},
    }

    # Discover and load data
    p_files = _discover_files(primary_dir, [symbol])
    s_files = _discover_files(secondary_dir, [symbol])

    if not p_files.get(symbol):
        result["sources"]["primary"] = {"status": "MISSING", "files_found": 0}
    if not s_files.get(symbol):
        result["sources"]["secondary"] = {"status": "MISSING", "files_found": 0}

    primary_raw = _load_data(p_files.get(symbol, []))
    secondary_raw = _load_data(s_files.get(symbol, []))

    result["sources"]["primary"] = {
        "status": "OK" if not primary_raw.empty else "MISSING",
        "files_found": len(p_files.get(symbol, [])),
        "rows": len(primary_raw),
        "date_range": (
            [str(primary_raw["timestamp"].min()), str(primary_raw["timestamp"].max())]
            if not primary_raw.empty else None
        ),
    }
    result["sources"]["secondary"] = {
        "status": "OK" if not secondary_raw.empty else "MISSING",
        "files_found": len(s_files.get(symbol, [])),
        "rows": len(secondary_raw),
        "date_range": (
            [str(secondary_raw["timestamp"].min()), str(secondary_raw["timestamp"].max())]
            if not secondary_raw.empty else None
        ),
    }

    # Filter by date range
    if not primary_raw.empty and start:
        primary_raw = primary_raw[primary_raw["timestamp"] >= pd.Timestamp(start, tz="UTC")].copy()
    if not primary_raw.empty and end:
        primary_raw = primary_raw[primary_raw["timestamp"] < pd.Timestamp(end, tz="UTC")].copy()
    if not secondary_raw.empty and start:
        secondary_raw = secondary_raw[secondary_raw["timestamp"] >= pd.Timestamp(start, tz="UTC")].copy()
    if not secondary_raw.empty and end:
        secondary_raw = secondary_raw[secondary_raw["timestamp"] < pd.Timestamp(end, tz="UTC")].copy()

    # Resample to 1-minute OHLCV
    primary_1m = _resample_ohlcv(primary_raw, "1min")
    secondary_1m = _resample_ohlcv(secondary_raw, "1min")

    result["data_summary"] = {
        "primary_bars": len(primary_1m),
        "secondary_bars": len(secondary_1m),
        "period_filter": {"start": start, "end": end},
    }

    # Run checks
    result["checks"]["price_alignment"] = check_price_alignment(primary_1m, secondary_1m, tolerance)
    result["checks"]["spread_comparison"] = check_spread_comparison(primary_1m, secondary_1m)
    result["checks"]["tick_density"] = check_tick_density(primary_1m, secondary_1m)
    result["checks"]["correlation"] = check_correlation(primary_1m, secondary_1m, corr_threshold)
    result["checks"]["gaps"] = check_gaps(primary_1m, secondary_1m)

    # Overall
    statuses = [c.get("status", "SKIP") for c in result["checks"].values()]
    if "FAIL" in statuses:
        result["overall"] = "FAIL"
    elif "WARN" in statuses:
        result["overall"] = "WARN"
    elif all(s == "SKIP" for s in statuses):
        result["overall"] = "SKIP"
    else:
        result["overall"] = "PASS"

    return result


# ---------------------------------------------------------------------------
# Single-Source Validation
# ---------------------------------------------------------------------------

def _check_ohlcv_invariants(df: pd.DataFrame) -> Dict[str, Any]:
    """Check OHLCV invariant violations: high >= low, high >= close, etc."""
    issues = []
    if "high" in df.columns and "low" in df.columns:
        n_bad = int((df["high"] < df["low"]).sum())
        if n_bad:
            issues.append(f"{n_bad} high<low violations")
    if "high" in df.columns and "close" in df.columns:
        n_bad = int((df["high"] < df["close"]).sum())
        if n_bad:
            issues.append(f"{n_bad} high<close violations")
    if "low" in df.columns and "close" in df.columns:
        n_bad = int((df["low"] > df["close"]).sum())
        if n_bad:
            issues.append(f"{n_bad} low>close violations")
    return {
        "violations": issues,
        "status": "PASS" if not issues else "WARN",
    }


def _check_data_completeness(df: pd.DataFrame, freq_minutes: int = 1) -> Dict[str, Any]:
    """Check for gaps in the time series."""
    if df.empty or len(df) < 2:
        return {"expected_bars": 0, "actual_bars": len(df), "gap_pct": 0, "gaps_found": 0, "status": "SKIP"}
    
    freq = f"{freq_minutes}min"
    full_range = pd.date_range(df.index[0], df.index[-1], freq=freq, tz="UTC")
    expected = len(full_range)
    actual = len(df)
    gap_pct = round((1 - actual / max(expected, 1)) * 100, 2)
    
    # Find large gaps (>2x freq)
    deltas = df.index.to_series().diff()
    large_gaps = int((deltas > pd.Timedelta(minutes=freq_minutes * 2)).sum())
    
    status = "PASS" if gap_pct < 5 else ("WARN" if gap_pct < 20 else "FAIL")
    return {
        "expected_bars": expected,
        "actual_bars": actual,
        "gap_pct": gap_pct,
        "gaps_found": large_gaps,
        "status": status,
    }


def _check_spread_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze spread distribution: negative spreads, outliers, consistency."""
    if df.empty or "ask" not in df.columns or "bid" not in df.columns:
        return {"status": "SKIP"}
    
    spread = df["ask"] - df["bid"]
    neg_count = int((spread < 0).sum())
    zero_count = int((spread == 0).sum())
    p99 = float(spread.quantile(0.99))
    p50 = float(spread.median())
    
    issues = []
    if neg_count > 0:
        issues.append(f"{neg_count} negative spreads")
    if zero_count > len(df) * 0.01:
        issues.append(f"{zero_count} zero spreads ({zero_count/len(df)*100:.1f}%)")
    
    return {
        "negative_spreads": neg_count,
        "zero_spreads": zero_count,
        "median_spread": round(p50, 6),
        "p99_spread": round(p99, 6),
        "violations": issues,
        "status": "PASS" if not issues else "WARN",
    }


def _check_stale_prices(df: pd.DataFrame, max_stale_minutes: int = 5) -> Dict[str, Any]:
    """Detect frozen quotes (same bid/ask for extended periods)."""
    if df.empty or "bid" not in df.columns:
        return {"status": "SKIP"}
    
    bid_stale = (df["bid"] == df["bid"].shift(1)).astype(int)
    # Count runs of stale quotes longer than max_stale_minutes
    stale_runs = 0
    current_run = 0
    for v in bid_stale:
        if v:
            current_run += 1
        else:
            if current_run >= max_stale_minutes:
                stale_runs += 1
            current_run = 0
    
    return {
        "stale_runs_over_5min": stale_runs,
        "pct_stale": round(float(bid_stale.mean() * 100), 2),
        "status": "PASS" if stale_runs < 10 else "WARN",
    }


def validate_symbol_single(
    symbol: str, primary_dir: str, start: str | None = None, end: str | None = None,
    db_path: str | None = None,
) -> Dict[str, Any]:
    """Validate a single symbol against quality expectations (no secondary source needed)."""
    result: Dict[str, Any] = {
        "symbol": symbol,
        "mode": "single_source",
        "checks": {},
        "overall": "PASS",
    }
    
    # Load data
    if db_path and os.path.exists(db_path):
        try:
            import duckdb
            conn = duckdb.connect(db_path)
            # Try available frequencies, prefer the highest resolution available
            freqs = conn.execute("SELECT DISTINCT frequency FROM ohlcv WHERE symbol = ?", [symbol]).fetchdf()["frequency"].tolist()
            if not freqs:
                raise ValueError(f"No data for {symbol}")
            # Prefer M1 > M5 > M15 > H1 > D1
            for pref in ["M1", "M5", "M15", "H1", "D1"]:
                if pref in freqs:
                    use_freq = pref
                    break
            else:
                use_freq = freqs[0]
            time_col = "time"
            query = f'SELECT "{time_col}" AS timestamp, open, high, low, close, volume FROM ohlcv WHERE symbol = ? AND frequency = ? ORDER BY timestamp'
            df = conn.execute(query, [symbol, use_freq]).fetchdf()
            conn.close()
        except Exception:
            df = pd.DataFrame()
    else:
        files = _discover_files(primary_dir, [symbol]).get(symbol, [])
        df = _load_data(files) if files else pd.DataFrame()
    
    if df.empty:
        result["overall"] = "SKIP"
        result["error"] = "No data found"
        return result
    
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    
    result["data_summary"] = {
        "bars": len(df),
        "columns": list(df.columns),
        "date_range": f"{df.index[0]} to {df.index[-1]}",
    }
    
    result["checks"]["ohlcv_invariants"] = _check_ohlcv_invariants(df)
    result["checks"]["spread_quality"] = _check_spread_quality(df)
    result["checks"]["stale_prices"] = _check_stale_prices(df)
    
    # Completeness check - try to infer frequency
    if len(df) > 1:
        deltas = df.index.to_series().diff().dropna()
        median_delta = deltas.median()
        freq_min = max(1, int(median_delta.total_seconds() / 60))
        result["checks"]["completeness"] = _check_data_completeness(df, freq_min)
    else:
        result["checks"]["completeness"] = {"status": "SKIP"}
    
    # Overall
    statuses = [c.get("status", "SKIP") for c in result["checks"].values()]
    if "FAIL" in statuses:
        result["overall"] = "FAIL"
    elif "WARN" in statuses:
        result["overall"] = "WARN"
    elif all(s == "SKIP" for s in statuses):
        result["overall"] = "SKIP"
    else:
        result["overall"] = "PASS"
    
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-Source Data Validator — compare price data across sources"
    )
    parser.add_argument(
        "--primary", required=True,
        help="Primary data source directory (e.g., MT5 warehouse path)",
    )
    parser.add_argument(
        "--secondary", default=None,
        help="Secondary data source directory (e.g., Dukascopy warehouse path)",
    )
    parser.add_argument(
        "--single-source", action="store_true",
        help="Validate against quality expectations (no secondary source needed)",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="DuckDB warehouse path (alternative to --primary directory)",
    )
    parser.add_argument(
        "--symbols", default="EURUSD,GBPUSD,XAUUSD",
        help="Comma-separated list of symbols (default: EURUSD,GBPUSD,XAUUSD)",
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date (ISO format, e.g. 2024-01-01)",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date (ISO format, e.g. 2024-01-31)",
    )
    parser.add_argument(
        "--output", "-o", default=DEFAULT_OUTPUT,
        help=f"Output directory for JSON reports (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--tolerance", type=float, default=0.0001,
        help="Price tolerance as fraction (default: 0.0001 = 0.01%%)",
    )
    parser.add_argument(
        "--correlation-threshold", type=float, default=0.95,
        help="Minimum acceptable Pearson r (default: 0.95)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Number of parallel symbol workers (default: 4)",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("ERROR: No symbols specified")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    primary_dir = os.path.abspath(args.primary)

    if not os.path.isdir(primary_dir):
        print(f"WARNING: Primary directory not found: {primary_dir}")

    single_source = args.single_source or not args.secondary
    if single_source:
        print("[SINGLE-SOURCE] Validating against quality expectations (no secondary source)")
    else:
        secondary_dir = os.path.abspath(args.secondary)
        if not os.path.isdir(secondary_dir):
            print(f"WARNING: Secondary directory not found: {secondary_dir}")

    start_time = time.time()

    # Run per-symbol validation in parallel
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for sym in symbols:
            if single_source:
                futures.append(
                    pool.submit(
                        validate_symbol_single,
                        sym, primary_dir, args.start, args.end, args.db_path,
                    )
                )
            else:
                futures.append(
                    pool.submit(
                        validate_symbol,
                        sym, primary_dir, secondary_dir,
                        args.start, args.end,
                        args.tolerance, args.correlation_threshold,
                    )
                )
        for f in futures:
            try:
                results.append(f.result())
            except Exception as e:
                results.append({
                    "symbol": "unknown",
                    "error": str(e),
                    "overall": "ERROR",
                })

    # Global report
    overalls = [r.get("overall", "ERROR") for r in results]
    if "FAIL" in overalls:
        global_status = "FAIL"
    elif "ERROR" in overalls:
        global_status = "FAIL"
    elif "WARN" in overalls:
        global_status = "WARN"
    elif "SKIP" in overalls and all(o == "SKIP" for o in overalls):
        global_status = "SKIP"
    else:
        global_status = "PASS"

    report: Dict[str, Any] = {
        "cross_source_report": {
            "primary": primary_dir,
            "secondary": secondary_dir if not single_source else None,
            "mode": "single_source" if single_source else "cross_source",
            "symbols": symbols,
            "period": {"start": args.start, "end": args.end},
            "parameters": {
                "tolerance": args.tolerance,
                "correlation_threshold": args.correlation_threshold,
            },
        },
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": results,
        "overall": global_status,
        "elapsed_seconds": round(time.time() - start_time, 2),
    }

    # Write per-symbol + global reports
    for res in results:
        sym = res.get("symbol", "unknown")
        sym_path = os.path.join(args.output, f"{sym}_cross_validation.json")
        with open(sym_path, "w") as f:
            json.dump(res, f, indent=2, default=str)
        print(f"  [{res.get('overall', 'ERROR'):>4}] {sym} -> {sym_path}")

    global_path = os.path.join(args.output, "cross_validation_report.json")
    with open(global_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nGlobal report: {global_path}")
    print(f"Overall: {global_status} ({round(time.time() - start_time, 1)}s)")

    if global_status == "FAIL":
        sys.exit(2)
    elif global_status == "WARN":
        sys.exit(1)


if __name__ == "__main__":
    main()
