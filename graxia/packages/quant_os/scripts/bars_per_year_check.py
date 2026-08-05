"""
bars_per_year_check.py

Diagnostic script for the pooled multi-asset TSMOM pre-registration
(quant_os). Validates that "D1" bars are actually consistent across
all 8 assets before the pooled backtest / Driscoll-Kraay SE calc is
built on top of them.

Checks performed per asset:
  1. Bars-per-calendar-year vs expected trading-day calendar
  2. Modal (most common) time delta between consecutive bars
     -> reveals if a "D1" file is secretly intraday / multi-session
  3. Weekend bar presence (should be absent for FX/equity/commodity,
     present for crypto)
  4. Duplicate timestamps
  5. Max gap between consecutive bars (business days)
  6. Sample timestamp inspection (first 20 rows + delta in hours)

Usage:
    python scripts/bars_per_year_check.py
"""

import sys
from pathlib import Path

import pandas as pd
from collections import Counter

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------

ASSET_FILES = {
    "XAUUSD": ROOT / "data" / "XAUUSD_D1.csv",
    "XAGUSD": ROOT / "data" / "XAGUSD_D1.csv",
    "EURUSD": ROOT / "data" / "EURUSD_D1.csv",
    "GBPUSD": ROOT / "data" / "GBPUSD_D1.csv",
    "USDJPY": ROOT / "data" / "USDJPY_D1.csv",
    "NAS100": ROOT / "data" / "NAS100_D1.csv",
    "US30":   ROOT / "data" / "US30_D1.csv",
    "BTCUSD": ROOT / "data" / "BTCUSD_D1.csv",
}

ASSET_CLASS = {
    "XAUUSD": "commodity", "XAGUSD": "commodity",
    "EURUSD": "fx", "GBPUSD": "fx", "USDJPY": "fx",
    "NAS100": "equity", "US30": "equity",
    "BTCUSD": "crypto",
}

EXPECTED_BARS_PER_YEAR = {
    "fx": 252,
    "equity": 252,
    "commodity": 252,
    "crypto": 365,
}

TOLERANCE_PCT = 15

TIMESTAMP_COL_CANDIDATES = ["timestamp", "time", "date", "Date", "Datetime", "datetime"]


# ---------------------------------------------------------------
# Loader
# ---------------------------------------------------------------

def load_asset_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path)

    ts_col = next((c for c in TIMESTAMP_COL_CANDIDATES if c in df.columns), None)
    if ts_col is None:
        raise ValueError(
            f"No timestamp column found in {path.name}. "
            f"Columns present: {list(df.columns)}. "
            f"Add the actual column name to TIMESTAMP_COL_CANDIDATES."
        )

    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.sort_values(ts_col).reset_index(drop=True)
    df = df.rename(columns={ts_col: "timestamp"})

    # Filter to >= 2005-01-01 (pre-registered pooled test window)
    df = df[df["timestamp"] >= "2005-01-01"].reset_index(drop=True)

    return df


# ---------------------------------------------------------------
# Checks
# ---------------------------------------------------------------

def modal_bar_interval(df: pd.DataFrame) -> pd.Timedelta:
    deltas = df["timestamp"].diff().dropna()
    rounded = deltas.dt.round("min")
    counts = Counter(rounded)
    return counts.most_common(1)[0][0] if counts else pd.Timedelta(0)


def weekend_bar_count(df: pd.DataFrame) -> int:
    return int(df["timestamp"].dt.dayofweek.isin([5, 6]).sum())


def duplicate_timestamp_count(df: pd.DataFrame) -> int:
    return int(df["timestamp"].duplicated().sum())


def max_gap_business_days(df: pd.DataFrame) -> float:
    deltas = df["timestamp"].diff().dropna()
    if deltas.empty:
        return 0.0
    return deltas.max() / pd.Timedelta(days=1)


def full_year_span(df: pd.DataFrame) -> float:
    span = (df["timestamp"].max() - df["timestamp"].min()).days
    return span / 365.25 if span > 0 else 0.0


def guess_cause(actual: float, expected: float) -> str:
    if not expected:
        return ""
    ratio = actual / expected
    if abs(ratio - 1) < 0.15:
        return ""
    known = [
        (2, "possible 2 bars/day (12h bars mislabeled as D1)"),
        (3, "possible 3 bars/day (8h bars mislabeled as D1)"),
        (4, "possible 4 bars/day (6h bars mislabeled as D1)"),
        (6, "possible 4h bars mislabeled as D1"),
        (7 / 5, "possible 7-day week counted instead of 5 (no weekend exclusion)"),
    ]
    for divisor, label in known:
        if abs(ratio - divisor) < 0.3:
            return label
    if ratio > 1:
        return f"~{ratio:.1f}x expected — investigate data source / session structure"
    return f"~{ratio:.1f}x expected — fewer bars than expected, check for missing data/gaps"


# ---------------------------------------------------------------
# Main report
# ---------------------------------------------------------------

def run_report():
    rows = []
    samples = {}

    for symbol, path in ASSET_FILES.items():
        try:
            df = load_asset_data(path)
        except Exception as e:
            print(f"[SKIP] {symbol}: {e}")
            continue

        n_bars = len(df)
        years = full_year_span(df)
        bars_per_year_actual = n_bars / years if years > 0 else float("nan")

        asset_class = ASSET_CLASS.get(symbol, "unknown")
        expected = EXPECTED_BARS_PER_YEAR.get(asset_class)
        deviation_pct = (
            100 * (bars_per_year_actual - expected) / expected if expected else float("nan")
        )
        verdict = "FLAG" if expected and abs(deviation_pct) > TOLERANCE_PCT else "OK"
        cause_hint = guess_cause(bars_per_year_actual, expected) if expected else ""

        modal_interval = modal_bar_interval(df)
        n_weekend = weekend_bar_count(df)
        n_dupes = duplicate_timestamp_count(df)
        max_gap = max_gap_business_days(df)

        weekend_flag = ""
        if asset_class in ("fx", "equity", "commodity") and n_weekend > 0:
            weekend_flag = f"UNEXPECTED_WEEKEND_BARS={n_weekend}"
        elif asset_class == "crypto" and n_weekend == 0:
            weekend_flag = "NO_WEEKEND_BARS (unexpected for crypto)"

        rows.append({
            "symbol": symbol,
            "class": asset_class,
            "n_bars": n_bars,
            "date_range_years": round(years, 2),
            "bars_per_year_actual": round(bars_per_year_actual, 1),
            "bars_per_year_expected": expected,
            "deviation_pct": round(deviation_pct, 1) if expected else None,
            "verdict": verdict,
            "cause_hint": cause_hint,
            "modal_bar_interval": str(modal_interval),
            "n_duplicate_timestamps": n_dupes,
            "max_gap_days": round(max_gap, 1),
            "weekend_bars": n_weekend,
            "weekend_flag": weekend_flag,
        })

        sample = df.head(20)[["timestamp"]].copy()
        sample["delta_hours"] = sample["timestamp"].diff().dt.total_seconds() / 3600
        samples[symbol] = sample

    report_df = pd.DataFrame(rows)

    print("=" * 110)
    print("BARS-PER-YEAR CONSISTENCY REPORT")
    print("=" * 110)
    if report_df.empty:
        print("No assets loaded successfully — check ASSET_FILES paths.")
        return report_df, samples

    print(report_df.drop(columns=["cause_hint"]).to_string(index=False))

    print("\n" + "=" * 110)
    print(f"FLAGGED ASSETS (bars/year deviates > {TOLERANCE_PCT}% from expected)")
    print("=" * 110)
    flagged = report_df[report_df["verdict"] == "FLAG"]
    if flagged.empty:
        print("None — all assets within tolerance. Safe to proceed to engine adaptation.")
    else:
        print(flagged[["symbol", "bars_per_year_actual", "bars_per_year_expected",
                        "deviation_pct", "cause_hint"]].to_string(index=False))
        print("\n^ Resolve these BEFORE building the multi-asset engine — the pooled")
        print("  lookback=252 and Driscoll-Kraay date-clustering both assume 1 bar = 1 trading day.")

    print("\n" + "=" * 110)
    print("WEEKEND / DUPLICATE / GAP WARNINGS")
    print("=" * 110)
    warn_df = report_df[
        (report_df["weekend_flag"] != "") |
        (report_df["n_duplicate_timestamps"] > 0) |
        (report_df["max_gap_days"] > 5)
    ]
    if warn_df.empty:
        print("None.")
    else:
        print(warn_df[["symbol", "weekend_flag", "n_duplicate_timestamps", "max_gap_days"]]
              .to_string(index=False))

    print("\n" + "=" * 110)
    print("SAMPLE TIMESTAMP INSPECTION (first 20 bars per asset)")
    print("=" * 110)
    for symbol, sample in samples.items():
        print(f"\n--- {symbol} ---")
        print(sample.to_string(index=False))

    return report_df, samples


if __name__ == "__main__":
    run_report()
