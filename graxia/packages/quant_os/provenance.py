"""Provenance-checked OHLCV loading for backtests.

Guards against synthetic backfill contamination. The raw ``*_D1.csv`` files
contain impossible pre-inception rows (e.g. EURUSD 1971, NAS100 1938,
XAUUSD 1793) that are flat O=H=L=C with placeholder volume -- synthetic
backfill, not market data. The core ``load_csv_data`` loader reads the
WHOLE file with no date slice, so any study that calls it directly would
train on two centuries of invented candles.

This module is the mandated loader for WS-A (trial 1028): it slices each
series to a provenance-checked window and HARD-FAILS if the resulting
slice still contains impossible dates or an egregious synthetic tell.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

# Real instrument inception (hard floor). Rows before this are impossible.
PROVENANCE_FLOOR: dict[str, str] = {
    "XAUUSD": "1971-01-01",  # gold floated 1971-08 (fixed before)
    "XAGUSD": "1971-01-01",
    "EURUSD": "1999-01-04",  # euro launched 1999-01-01
    "GBPUSD": "1971-01-01",  # post-Smithsonian floats
    "USDJPY": "1971-01-01",
    "NAS100": "1985-01-01",  # Nasdaq-100 launched 1985-01
    "US30": "1896-05-27",  # DJIA continuous history
}

# Default slice start for modern-era studies (WS-A pre-reg window).
DEFAULT_SLICE_START = "2005-01-01"

# Placeholder volumes that flag synthetic backfill candles.
SYNTH_VOLUME_PLACEHOLDERS = frozenset({0.0, 1.0})


class DataProvenanceError(Exception):
    """Raised when a series fails provenance checks."""


class UncalibratedCostError(Exception):
    """Raised when a trial requests a symbol with no verified cost-calibration data."""


# Kept in sync with config/tradeable_universe.json's "tradeable" list.
# A symbol here has real (if not yet multi-day) cost measurement; anything
# else has none. Trial #1030 (2026-07-30) traded 16 assets through a
# bespoke loader that skipped this check and used a flat assumed cost
# instead of real ones — invalidated after the fact (see invalidation_note
# on trial 1030 in research/hypothesis_registry.json). This constant is
# the same category of mistake already caught once in commit 33b90c31.
COST_CALIBRATED_SYMBOLS = frozenset({"XAUUSD", "USOIL", "USDJPY"})


def require_cost_calibrated(symbol: str) -> None:
    """Refuse a symbol with no verified cost-calibration data.

    This only protects callers that route through this module. A script
    that defines its own CSV loader (as trial #1030's did) bypasses it
    entirely — this is a real gap, not full enforcement. See
    research/trial_ledger.json's trial_cap_1022_reached note for the
    reconciliation record of that specific bypass.
    """
    if symbol not in COST_CALIBRATED_SYMBOLS:
        raise UncalibratedCostError(
            f"{symbol!r} has no verified cost-calibration data in "
            f"config/tradeable_universe.json's 'tradeable' list "
            f"({sorted(COST_CALIBRATED_SYMBOLS)}). Running a trial against "
            f"an assumed/synthetic cost model is exactly the fabrication "
            f"pattern already caught twice (commit 33b90c31, trial #1030). "
            f"Add real cost data to config/tradeable_universe.json first, "
            f"or pass require_cost_calibration=False if this call is not "
            f"informing a trading decision."
        )


# The tsm_*.py scripts (tsm_backtest/tsm_ema/tsm_portfolio/tsm_validate) share
# one ASSETS list using data-source-suffixed names (e.g. "EURUSD_YF" for a
# Yahoo Finance column) rather than the canonical symbols this module and
# tradeable_universe.json use. Maps each to the canonical symbol so all four
# scripts can share one gate call instead of four bespoke ones.
TSM_ASSET_ALIASES: dict[str, str] = {
    "EURUSD_YF": "EURUSD",
    "GBPUSD_YF": "GBPUSD",
    "BTC_YF": "BTCUSD",
    "ETH_YF": "ETHUSD",
    "SILVER": "XAGUSD",
    "OIL": "USOIL",
}


def require_cost_calibrated_tsm_asset(asset: str) -> None:
    """require_cost_calibrated, resolving tsm_*.py's aliased asset names first."""
    require_cost_calibrated(TSM_ASSET_ALIASES.get(asset, asset))


def _read_raw(symbol: str, data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, str]:
    path = data_dir / f"{symbol}_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df.sort_values(ts).reset_index(drop=True)
    return df, ts


def load_provenance_checked(
    symbol: str,
    slice_start: str = DEFAULT_SLICE_START,
    slice_end: str | None = None,
    data_dir: Path = DATA_DIR,
    max_synth_fraction: float = 0.10,
    require_cost_calibration: bool = True,
) -> pd.DataFrame:
    """Load D1 OHLCV sliced to a provenance-checked window.

    Hard-fails if:
      * ``require_cost_calibration`` is True (the default) and the symbol
        has no verified cost data (see ``require_cost_calibrated``),
      * any row in the slice has date < PROVENANCE_FLOOR[symbol]
        (impossible-date contamination leaked into the slice), or
      * the synthetic-backfill tell (flat O=H=L=C with placeholder volume)
        exceeds ``max_synth_fraction`` of the slice.

    The primary guard is the impossible-date check: with slice_start=2005
    every WS-A symbol's floor is <= 2005, so all backfill is excluded. The
    synth-tell check is a secondary backstop against modern-window leakage.
    """
    if require_cost_calibration:
        require_cost_calibrated(symbol)
    df, ts = _read_raw(symbol, data_dir)
    floor = pd.Timestamp(PROVENANCE_FLOOR[symbol])
    start = pd.Timestamp(slice_start)
    end = pd.Timestamp(slice_end) if slice_end else df[ts].max()

    sliced = df[(df[ts] >= start) & (df[ts] <= end)].copy()

    impossible = sliced[sliced[ts] < floor]
    if len(impossible):
        raise DataProvenanceError(
            f"{symbol}: {len(impossible)} rows in slice have impossible dates (< {floor.date()}); data contaminated."
        )

    flat = (sliced["open"] == sliced["high"]) & (sliced["high"] == sliced["low"]) & (sliced["low"] == sliced["close"])
    synth = flat & (sliced["volume"].isin(SYNTH_VOLUME_PLACEHOLDERS))
    frac = synth.sum() / len(sliced)
    if frac > max_synth_fraction:
        raise DataProvenanceError(
            f"{symbol}: synthetic tell in {frac:.2%} of slice (> {max_synth_fraction:.2%}); data contaminated."
        )
    return sliced.reset_index(drop=True)


def verify_modern_slice(
    symbols: list[str],
    slice_start: str = DEFAULT_SLICE_START,
    data_dir: Path = DATA_DIR,
) -> dict[str, dict]:
    """Return a provenance report for each symbol's modern slice.

    Reports (does not raise): row count, date range, flat-candle fraction,
    synthetic-tell fraction, volume-zero fraction, max date gap, and how
    many raw rows fall before the provenance floor (backfill magnitude).
    """
    report: dict[str, dict] = {}
    for s in symbols:
        df, ts = _read_raw(s, data_dir)
        floor = pd.Timestamp(PROVENANCE_FLOOR[s])
        m = df[df[ts] >= slice_start]
        flat = (m["open"] == m["high"]) & (m["high"] == m["low"]) & (m["low"] == m["close"])
        synth = flat & (m["volume"].isin(SYNTH_VOLUME_PLACEHOLDERS))
        gaps = m[ts].diff().dt.days.dropna()
        report[s] = {
            "modern_rows": int(len(m)),
            "date_min": str(m[ts].min().date()),
            "date_max": str(m[ts].max().date()),
            "flat_fraction": round(float(flat.mean()), 4),
            "synth_fraction": round(float(synth.mean()), 4),
            "vol_zero_fraction": round(float((m["volume"] == 0).mean()), 4),
            "max_gap_days": int(gaps.max()) if len(gaps) else 0,
            "rows_before_floor": int((df[ts] < floor).sum()),
        }
    return report
