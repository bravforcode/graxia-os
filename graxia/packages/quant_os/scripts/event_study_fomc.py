"""
FOMC Event Study — retail version of Kensho-style event analysis.

Uses free FRED + yfinance data to measure asset drift around FOMC
announcements. Mirrors the "what happened after last 10 Fed rate hikes"
analysis but for any symbol and date range.

Usage:
    python scripts/event_study_fomc.py --symbol XAUUSD --window 48
    python scripts/event_study_fomc.py --symbol EURUSD --window 24 --start 2020-01-01
    python scripts/event_study_fomc.py --symbol BTCUSD --window 72 --fred-key YOUR_KEY

Dependencies:
    numpy, pandas (required)
    yfinance (optional — installed via: pip install yfinance)
    fredapi (optional — for live FOMC dates from FRED)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# ── Fallback FOMC Dates (sourced from run_rydc_validation.py, 2020–2026) ──
FOMC_DATES: list[str] = [
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28",
    "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27",
    "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
    "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-17",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-16",
]


# ── Result Container ──
@dataclass(frozen=True)
class EventStudyResult:
    """Immutable container for event study results."""

    symbol: str
    n_events: int
    pre_window: int
    post_window: int
    avg_return: float  # percentage
    median_return: float  # percentage
    std_return: float  # percentage
    t_stat: float
    p_value: float
    hit_rate: float  # fraction positive, 0-1
    event_returns: list[float] = field(repr=False)
    event_dates: list[str] = field(repr=False)


# ── FRED API (optional) ──
def fetch_fomc_dates_fred(api_key: str | None = None) -> list[str]:
    """Try to fetch FOMC dates from FRED API.

    Falls back to hardcoded FOMC_DATES if:
      - No API key provided
      - fredapi not installed
      - Network/API error
    """
    if api_key is None:
        print("[info] No FRED API key, using hardcoded FOMC dates")
        return list(FOMC_DATES)

    try:
        from fredapi import Fred
    except ImportError:
        print("[warn] fredapi not installed, using hardcoded FOMC dates")
        return list(FOMC_DATES)

    try:
        fred = Fred(api_key=api_key)
        # FRED series for FOMC dates: "FEDTARMD" (target federal funds rate, changes)
        series = fred.get_series("FEDTARMD")
        # Dates where rate changed → approximate FOMC meeting dates
        dates = series.dropna().index.strftime("%Y-%m-%d").tolist()
        if not dates:
            print("[warn] FRED returned empty series, using hardcoded dates")
            return list(FOMC_DATES)
        print(f"[info] Fetched {len(dates)} dates from FRED")
        return dates
    except Exception as exc:
        print(f"[warn] FRED API error ({exc}), using hardcoded dates")
        return list(FOMC_DATES)


# ── Price Data ──
def fetch_price_data(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1h",
) -> pd.DataFrame:
    """Fetch OHLCV data via yfinance.

    Translates common symbols:
      XAUUSD → GC=F (gold futures)
      EURUSD → EURUSD=X
      BTCUSD → BTC-USD

    Returns DataFrame with columns: Open, High, Low, Close, Volume
    and a DatetimeIndex (UTC-normalized).
    """
    try:
        import yfinance as yf
    except ImportError:
        print("[error] yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    ticker_map = {
        "XAUUSD": "GC=F",
        "EURUSD": "EURUSD=X",
        "BTCUSD": "BTC-USD",
        "BTCUSDT": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "ETHUSDT": "ETH-USD",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
    }
    ticker = ticker_map.get(symbol.upper(), symbol)
    print(f"[info] Fetching {symbol} → ticker={ticker}, {start} → {end}, interval={interval}")

    data = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker} ({start} → {end})")

    # Flatten multi-level columns if present (yfinance >= 0.2.31)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data.index = pd.to_datetime(data.index, utc=True)
    print(f"[info] Got {len(data)} bars ({data.index[0]} → {data.index[-1]})")
    return data


# ── Core Event Return Computation ──
def compute_event_returns(
    prices: pd.DataFrame,
    fomc_dates: list[str],
    pre_window: int = 24,
    post_window: int = 48,
) -> pd.DataFrame:
    """Compute returns around each FOMC event.

    For each FOMC date:
      - Finds the nearest bar on or after the announcement (14:00 ET / 18:00 UTC)
      - Computes return from [event - pre_window] to [event + post_window]
      - Returns a DataFrame with one row per event.

    Args:
        prices: OHLCV DataFrame with DatetimeIndex (UTC).
        fomc_dates: List of "YYYY-MM-DD" strings.
        pre_window: Hours before event to measure from.
        post_window: Hours after event to measure to.

    Returns:
        DataFrame with columns: event_date, pre_price, post_price, return_pct, n_bars
    """
    results: list[dict] = []

    # FOMC statement release is typically 14:00 ET = 18:00 UTC
    fomc_hour_utc = 18

    for date_str in fomc_dates:
        event_dt = pd.Timestamp(f"{date_str} {fomc_hour_utc:02d}:00:00", tz="UTC")

        # Skip if event is outside price data range entirely
        if event_dt < prices.index[0] or event_dt > prices.index[-1]:
            continue

        # Find nearest bar at or after event time
        post_mask = prices.index >= event_dt
        if not post_mask.any():
            continue
        post_idx = prices.index[post_mask][0]

        # Find bar at event - pre_window hours
        pre_dt = event_dt - timedelta(hours=pre_window)
        pre_mask = prices.index >= pre_dt
        if not pre_mask.any():
            continue
        pre_idx = prices.index[pre_mask][0]

        # Find bar at event + post_window hours
        target_post_dt = event_dt + timedelta(hours=post_window)
        post_end_mask = prices.index >= target_post_dt
        if not post_end_mask.any():
            # Use the last available bar
            post_end_idx = prices.index[-1]
        else:
            post_end_idx = prices.index[post_end_mask][0]

        pre_price = float(prices.loc[pre_idx, "Close"])
        post_price = float(prices.loc[post_end_idx, "Close"])
        ret_pct = (post_price / pre_price - 1.0) * 100.0

        # Count bars in window for data-quality check
        window_mask = (prices.index >= pre_idx) & (prices.index <= post_end_idx)
        n_bars = int(window_mask.sum())

        results.append(
            {
                "event_date": date_str,
                "pre_price": pre_price,
                "post_price": post_price,
                "return_pct": ret_pct,
                "n_bars": n_bars,
            }
        )

    return pd.DataFrame(results)


# ── Statistical Tests ──
def _ttest_1samp(data: np.ndarray, popmean: float = 0.0) -> tuple[float, float]:
    """One-sample t-test. Pure numpy — no scipy dependency.

    Returns (t_stat, two-sided p_value).
    """
    n = len(data)
    if n < 2:
        return (0.0, 1.0)
    mean = np.mean(data)
    std = np.std(data, ddof=1)
    if std == 0:
        return (0.0, 1.0)
    t_stat = (mean - popmean) / (std / np.sqrt(n))
    # Two-sided p-value via t-distribution CDF approximation
    # Using the Abramowitz & Stegun approximation for large n,
    # and a simple Beta regularized for small n.
    df = n - 1
    p_value = _t_cdf_two_sided(t_stat, df)
    return (float(t_stat), float(p_value))


def _t_cdf_two_sided(t: float, df: int) -> float:
    """Two-sided p-value from t-distribution using incomplete beta function.

    P(|T| > |t|) = 2 * (1 - I_{df/(df+t^2)}(df/2, 1/2))
    Uses scipy's betainc if available, else a simple normal approximation.
    """
    x = df / (df + t * t)
    try:
        from scipy.special import betainc
        p_one = 0.5 * betainc(df / 2.0, 0.5, x)
        return 2.0 * p_one
    except ImportError:
        # Normal approximation for large df
        # P(|Z| > |z|) ≈ 2 * (1 - Phi(|z|))
        abs_z = abs(t)
        # Abramowitz & Stegun approximation
        p_one = 0.5 * (1.0 + np.math.erf(abs_z / np.sqrt(2.0)))
        return 2.0 * (1.0 - p_one)


# ── Full Event Study ──
def run_event_study(
    symbol: str,
    fomc_dates: list[str] | None = None,
    pre_window: int = 24,
    post_window: int = 48,
    start: str = "2020-01-01",
    end: str | None = None,
    fred_key: str | None = None,
) -> EventStudyResult:
    """Run full FOMC event study.

    Steps:
      1. Resolve FOMC dates (FRED or hardcoded)
      2. Fetch price data
      3. Compute per-event returns
      4. Aggregate statistics + t-test
    """
    # 1. FOMC dates
    if fomc_dates is None:
        fomc_dates = fetch_fomc_dates_fred(fred_key)

    # Filter to date range
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = (
        datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
    )
    fomc_filtered = [
        d for d in fomc_dates
        if start_dt <= datetime.strptime(d, "%Y-%m-%d") <= end_dt
    ]
    print(f"[info] {len(fomc_filtered)} FOMC events in {start} → {end or 'now'}")

    if not fomc_filtered:
        return EventStudyResult(
            symbol=symbol,
            n_events=0,
            pre_window=pre_window,
            post_window=post_window,
            avg_return=0.0,
            median_return=0.0,
            std_return=0.0,
            t_stat=0.0,
            p_value=1.0,
            hit_rate=0.0,
            event_returns=[],
            event_dates=[],
        )

    # 2. Fetch prices — extend start to cover pre-window
    fetch_start = (
        datetime.strptime(start, "%Y-%m-%d") - timedelta(days=7)
    ).strftime("%Y-%m-%d")
    fetch_end = end or datetime.now().strftime("%Y-%m-%d")
    prices = fetch_price_data(symbol, fetch_start, fetch_end)

    # 3. Compute event returns
    returns_df = compute_event_returns(prices, fomc_filtered, pre_window, post_window)

    if returns_df.empty:
        print("[warn] No valid event returns computed")
        return EventStudyResult(
            symbol=symbol,
            n_events=0,
            pre_window=pre_window,
            post_window=post_window,
            avg_return=0.0,
            median_return=0.0,
            std_return=0.0,
            t_stat=0.0,
            p_value=1.0,
            hit_rate=0.0,
            event_returns=[],
            event_dates=[],
        )

    # 4. Aggregate
    rets = returns_df["return_pct"].values
    t_stat, p_value = _ttest_1samp(rets)
    hit_rate = float(np.mean(rets > 0))

    return EventStudyResult(
        symbol=symbol,
        n_events=len(rets),
        pre_window=pre_window,
        post_window=post_window,
        avg_return=float(np.mean(rets)),
        median_return=float(np.median(rets)),
        std_return=float(np.std(rets, ddof=1)),
        t_stat=t_stat,
        p_value=p_value,
        hit_rate=hit_rate,
        event_returns=rets.tolist(),
        event_dates=returns_df["event_date"].tolist(),
    )


# ── Pretty Print ──
def print_results(result: EventStudyResult, window: int) -> None:
    """Print formatted event study summary table."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  FOMC Event Study: {result.symbol}")
    print(f"  Window: -{result.pre_window}h → +{result.post_window}h around announcement")
    print(sep)

    if result.n_events == 0:
        print("  No events in range.")
        print(sep)
        return

    print(f"  Events analyzed:   {result.n_events}")
    print(f"  Avg return:        {result.avg_return:+.4f}%")
    print(f"  Median return:     {result.median_return:+.4f}%")
    print(f"  Std deviation:     {result.std_return:.4f}%")
    print(f"  t-statistic:       {result.t_stat:+.3f}")
    print(f"  p-value (2-sided): {result.p_value:.4f}")
    sig = "***" if result.p_value < 0.01 else "**" if result.p_value < 0.05 else "*" if result.p_value < 0.10 else ""
    print(f"  Significance:      {sig or 'n.s.'}")
    print(f"  Hit rate (↑):      {result.hit_rate * 100:.1f}%")
    print(sep)

    # Per-event table
    print(f"\n  {'Date':<12} {'Return':>10} {'Direction':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10}")
    for date, ret in zip(result.event_dates, result.event_returns):
        direction = "▲" if ret > 0 else "▼" if ret < 0 else "─"
        print(f"  {date:<12} {ret:>+9.4f}% {direction:>10}")
    print()


# ── CLI ──
def main() -> None:
    parser = argparse.ArgumentParser(
        description="FOMC Event Study — measure asset drift around Fed announcements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbol", default="XAUUSD",
        help="Asset symbol (default: XAUUSD). Options: XAUUSD, EURUSD, BTCUSD, etc.",
    )
    parser.add_argument(
        "--window", type=int, default=48,
        help="Post-event window in hours (default: 48)",
    )
    parser.add_argument(
        "--pre-window", type=int, default=24,
        help="Pre-event window in hours (default: 24)",
    )
    parser.add_argument(
        "--start", default="2020-01-01",
        help="Start date YYYY-MM-DD (default: 2020-01-01)",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD (default: now)",
    )
    parser.add_argument(
        "--fred-key", default=None,
        help="FRED API key for live FOMC dates (optional)",
    )
    args = parser.parse_args()

    result = run_event_study(
        symbol=args.symbol,
        pre_window=args.pre_window,
        post_window=args.window,
        start=args.start,
        end=args.end,
        fred_key=args.fred_key,
    )

    print_results(result, args.window)


if __name__ == "__main__":
    main()
