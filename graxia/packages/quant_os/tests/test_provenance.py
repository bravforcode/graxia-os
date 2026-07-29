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


def test_loader_hard_fails_on_impossible_dates():
    """Slicing EURUSD to before its 1999 floor must raise, not silently pass."""
    # EURUSD floor is 1999-01-04; asking for 1990->2005 includes impossible rows.
    try:
        load_provenance_checked("EURUSD", slice_start="1990-01-01")
        raise AssertionError("expected DataProvenanceError for impossible-date slice")
    except DataProvenanceError:
        pass


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
    """Confirm the raw files DO contain backfill, proving the guard matters."""
    rep = verify_modern_slice(WS_A_UNIVERSE)
    # EURUSD has ~7079 rows before 1999; NAS100 ~12396 before 1985.
    assert rep["EURUSD"]["rows_before_floor"] > 1000
    assert rep["NAS100"]["rows_before_floor"] > 1000
    # ...but those rows are NOT in the loaded slice
    df = load_provenance_checked("EURUSD")
    assert (df["time"] < "1999-01-01").sum() == 0
