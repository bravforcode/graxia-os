"""Unit tests for the JSON-backed cost-calibration gate (Phase 1).

Uses a synthetic universe fixture via monkeypatch of provenance.UNIVERSE_PATH —
never asserts against the live config file, so these tests are order-independent
of the Task 12 activation migration.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

import provenance
from provenance import UncalibratedCostError

FIXTURE_UNIVERSE = {
    "tradeable": [{"symbol": "XAUUSD"}],
    "measuring": [{"symbol": "USOIL"}],
    "verifying": [{"symbol": "USDJPY"}],
    "candidate": [{"symbol": "EURUSD"}],
    "excluded": [{"symbol": "GBPUSD", "reason": "no data"}],
}


@pytest.fixture()
def universe(tmp_path, monkeypatch):
    path = tmp_path / "tradeable_universe.json"
    path.write_text(json.dumps(FIXTURE_UNIVERSE))
    monkeypatch.setattr(provenance, "UNIVERSE_PATH", path)
    return path


def test_live_mode_is_tradeable_only(universe):
    assert provenance.cost_calibrated_symbols(mode="live") == frozenset({"XAUUSD"})


def test_paper_mode_is_superset(universe):
    assert provenance.cost_calibrated_symbols(mode="paper") == frozenset({"XAUUSD", "USOIL", "USDJPY"})


def test_candidate_and_excluded_never_allowed(universe):
    for mode in ("paper", "live"):
        assert "EURUSD" not in provenance.cost_calibrated_symbols(mode=mode)
        assert "GBPUSD" not in provenance.cost_calibrated_symbols(mode=mode)


def test_live_raises_for_measuring_symbol(universe):
    with pytest.raises(UncalibratedCostError, match="USOIL"):
        provenance.require_cost_calibrated("USOIL", mode="live")


def test_paper_allows_measuring_symbol_and_returns_status(universe):
    assert provenance.require_cost_calibrated("USOIL", mode="paper") == "measuring"


def test_paper_allows_verifying_symbol_and_returns_status(universe):
    assert provenance.require_cost_calibrated("USDJPY", mode="paper") == "verifying"


def test_unknown_symbol_raises_in_both_modes(universe):
    for mode in ("paper", "live"):
        with pytest.raises(UncalibratedCostError, match="SOLUSD"):
            provenance.require_cost_calibrated("SOLUSD", mode=mode)


def test_tsm_alias_resolution(universe):
    # OIL -> USOIL (measuring): paper passes with staleness flag; live raises.
    assert provenance.require_cost_calibrated_tsm_asset("OIL", mode="paper") == "measuring"
    with pytest.raises(UncalibratedCostError):
        provenance.require_cost_calibrated_tsm_asset("OIL", mode="live")
    # EURUSD_YF -> EURUSD (candidate): both modes raise.
    with pytest.raises(UncalibratedCostError):
        provenance.require_cost_calibrated_tsm_asset("EURUSD_YF", mode="paper")


def test_load_provenance_checked_paper_mode_allows_measuring_symbol(tmp_path, monkeypatch, universe):
    """load_provenance_checked gates with mode=paper by default, so a measuring
    symbol with valid data loads; a live-mode call on the same symbol raises
    before touching the data file."""
    csv_path = tmp_path / "USOIL_D1.csv"
    rows = []
    for i in range(30):
        day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        rows.append(
            {
                "time": day.isoformat(),
                "open": 70.0 + i * 0.01,
                "high": 70.0 + i * 0.01 + 0.1,
                "low": 70.0 + i * 0.01 - 0.1,
                "close": 70.0 + i * 0.01 + 0.05,
                "volume": 100.0,
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    # USOIL (a CFD) has no entry in the real PROVENANCE_FLOOR — that is a
    # pre-existing loader limitation, out of Phase 1 scope. Give it a floor
    # for this test only (PROVENANCE_FLOOR is read at call time).
    monkeypatch.setattr(
        provenance,
        "PROVENANCE_FLOOR",
        {**provenance.PROVENANCE_FLOOR, "USOIL": "2000-01-01"},
    )

    df = provenance.load_provenance_checked("USOIL", data_dir=tmp_path)  # default mode="paper"
    assert len(df) == 30

    with pytest.raises(UncalibratedCostError, match="USOIL"):
        provenance.load_provenance_checked("USOIL", mode="live", data_dir=tmp_path)
