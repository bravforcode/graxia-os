"""Provenance-checked data loading for backtests (WS-A / trial 1028).

Guards against synthetic backfill contamination: the raw *_D1.csv files
contain impossible pre-inception rows (EURUSD 1971, NAS100 1938, XAUUSD
1793) that are flat O=H=L=C with placeholder volume. This module must be
the ONLY loader WS-A uses, and these tests pin that contract.
"""

import sys
from pathlib import Path

# Make the graxia package importable when run from the quant_os dir
_GRAXIA_ROOT = Path(__file__).resolve().parents[3]
if str(_GRAXIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_GRAXIA_ROOT))

from graxia.packages.quant_os.provenance import (  # noqa: E402
    DataProvenanceError,
    load_provenance_checked,
    verify_modern_slice,
)

WS_A_UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]


def test_loader_excludes_pre_inception_backfill():
    """No row in any WS-A slice may predate 2005 (the pre-reg window)."""
    for sym in WS_A_UNIVERSE:
        df = load_provenance_checked(sym)
        assert df["time"].min().year >= 2005, f"{sym} slice starts before 2005"
        assert df["time"].max().year >= 2025, f"{sym} slice missing modern data"


def test_loader_passes_when_no_impossible_dates_in_slice():
    """Slicing EURUSD to before its 1999 floor returns only valid rows.

    The raw EURUSD_D1.csv was rebuilt (starts 2005), so requesting
    slice_start=1990 no longer includes impossible rows.  The loader
    must NOT raise — it just returns the valid 2005+ slice.
    """
    df = load_provenance_checked("EURUSD", slice_start="1990-01-01")
    assert len(df) > 0, "should return valid rows"
    assert df["time"].min().year >= 2005, "returned row predates 2005"


def test_modern_slice_is_real_not_frozen_backfill():
    """Modern slice must be daily-spaced with negligible synthetic tell."""
    rep = verify_modern_slice(WS_A_UNIVERSE)
    for sym, r in rep.items():
        # daily spacing: max gap should be a long weekend, not monthly backfill
        assert r["max_gap_days"] <= 7, f"{sym} has monthly-spaced gaps ({r['max_gap_days']}d)"
        # synthetic tell must be negligible (frozen backfill would be ~70%+)
        assert r["synth_fraction"] < 0.05, f"{sym} synth_fraction too high: {r['synth_fraction']}"
        # prices must actually move (flat fraction low)
        assert r["flat_fraction"] < 0.10, f"{sym} flat_fraction too high: {r['flat_fraction']}"


def test_backfill_magnitude_is_excluded():
    """Raw files were rebuilt — no backfill rows remain before provenance floor."""
    rep = verify_modern_slice(WS_A_UNIVERSE)
    # After rebuild: EURUSD starts 2005, NAS100 starts 2008. No pre-floor rows.
    assert rep["EURUSD"]["rows_before_floor"] == 0
    assert rep["NAS100"]["rows_before_floor"] == 0
    # ...and loaded slices contain no impossible dates
    df = load_provenance_checked("EURUSD")
    assert (df["time"] < "1999-01-01").sum() == 0


def test_bar_interval_assertion_passes_for_rebuilt_xauusd():
    """XAUUSD_D1.csv was rebuilt as true D1 (1 bar/day) — must pass."""
    df = load_provenance_checked("XAUUSD")
    assert len(df) > 0
    # Verify 1 bar per day
    dates = df["time"].dt.normalize()
    assert len(dates) == dates.nunique(), "XAUUSD should have 1 bar/day after rebuild"


def test_bar_interval_assertion_passes_single_bar_per_date():
    """Symbols with 1 bar/day must pass the bar-interval assertion."""
    # Test a few symbols that should have 1 bar/day
    for sym in ["XAGUSD", "EURUSD", "GBPUSD"]:
        try:
            df = load_provenance_checked(sym)
            # If we get here, the assertion passed
            assert len(df) > 0, f"{sym} loaded empty"
        except DataProvenanceError as e:
            if "multi-bar-per-date" in str(e).lower() or "unique dates" in str(e).lower():
                raise AssertionError(f"{sym} should have 1 bar/day but was blocked") from e
            raise
