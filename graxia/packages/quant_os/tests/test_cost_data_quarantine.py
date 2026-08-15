"""P0.3 — mock and unverified cost data must never reach a cost calculation.

The corpus-invalidating defect this whole phase exists to fix was a cost
number that looked measured and was not. Two files in `config/` still hold
data of that kind:

  * `cost_calibration_live.json` -- every asset `"status": "MOCK"`,
    `"source": "mock_from_d1"`, n=720 synthetic ticks.
  * `cost_calibration.json` -> NAS100 -- `"status": "UNVERIFIED_NO_DATA"`,
    a placeholder the file flags as unbacked by its own admission.

`SymbolCostProfile._UNUSABLE_STATUSES` rejects both at the point of use.
These tests lock that behaviour in, and -- more importantly -- assert that
no production module reads the mock file at all, so the guarantee cannot be
routed around by a future loader that never consults the status field.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from graxia.packages.quant_os.backtest.dynamic_spread_model import (
    _UNUSABLE_STATUSES,
    SymbolCostProfile,
    UnmeasuredCostError,
)

_PKG_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PKG_ROOT / "config"
_MOCK_FILE = "cost_calibration_live.json"

# Directories that ship as part of the running system. `scripts/` is excluded
# because measure_real_spread.py legitimately WRITES the mock file -- that is
# how it gets produced. `tests/` is excluded because this file names it.
_PRODUCTION_DIRS = (
    "backtest",
    "core",
    "execution",
    "risk",
    "strategies",
    "validation",
    "data",
    "api",
    "runtime",
    "paper_engine",
    "market_data",
)


def _assets(filename: str) -> dict:
    path = _CONFIG_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not present")
    return json.loads(path.read_text(encoding="utf-8")).get("assets", {})


# ---------------------------------------------------------------------------
# The data really is what we think it is
# ---------------------------------------------------------------------------


def test_mock_file_is_still_all_mock():
    """If someone measures these for real, this test should fail and be deleted."""
    assets = _assets(_MOCK_FILE)
    assert assets, "expected the mock calibration file to have assets"
    statuses = {sym: rec.get("status") for sym, rec in assets.items()}
    assert all(s == "MOCK" for s in statuses.values()), (
        f"cost_calibration_live.json is no longer uniformly MOCK: {statuses}. "
        "Either it was measured (delete this test and promote the data) or "
        "something wrote real-looking data into a mock file."
    )


def test_nas100_is_still_unverified():
    """NAS100 has no measured spread; the file says so."""
    rec = _assets("cost_calibration.json").get("NAS100")
    assert rec is not None, "NAS100 vanished from cost_calibration.json"
    assert rec["status"] == "UNVERIFIED_NO_DATA", (
        f"NAS100 status is now {rec['status']!r}. If it was genuinely measured, "
        "update this test; do not let a placeholder be silently promoted."
    )


# ---------------------------------------------------------------------------
# Unusable statuses are rejected at the point of use
# ---------------------------------------------------------------------------


def test_unusable_statuses_cover_both_kinds():
    assert frozenset({"MOCK", "UNVERIFIED_NO_DATA"}) == _UNUSABLE_STATUSES


def test_unverified_symbol_raises_rather_than_returning_placeholder():
    """NAS100 must fail loudly, not hand back its 1.3 bps placeholder."""
    with pytest.raises(UnmeasuredCostError) as exc:
        SymbolCostProfile.for_symbol("NAS100")
    assert "NAS100" in str(exc.value)


def test_unknown_symbol_raises_rather_than_substituting():
    """The original defect: an unmapped symbol silently got gold's costs.

    AUDUSD is deliberately NOT in cost_calibration.json (v4.1 SP3 calibrates
    XAUUSD/USDJPY/EURUSD/GBPUSD/BTCUSD/US30 + legacy NAS100/OIL — AUDUSD has
    never been measured). Kept as the unmapped probe so the guard is tested
    against a symbol that truly has no profile.
    """
    with pytest.raises(UnmeasuredCostError):
        SymbolCostProfile.for_symbol("AUDUSD")


def test_measured_symbol_still_resolves():
    """The guard must not be so broad that real measured data stops working."""
    profile = SymbolCostProfile.for_symbol("XAUUSD")
    assert profile.status not in _UNUSABLE_STATUSES
    assert profile.get_spread_bps() > 0


def test_unmeasured_slippage_raises_even_when_spread_is_measured():
    """XAUUSD's spread is FROM_TICKS but slippage_bps_measured is null.

    Per-term, not per-symbol: a measured spread must not license an invented
    slippage.
    """
    profile = SymbolCostProfile.for_symbol("XAUUSD")
    if profile.slippage_bps is None:
        with pytest.raises(UnmeasuredCostError):
            profile.get_slippage_bps()


# ---------------------------------------------------------------------------
# The mock file is not reachable from production code
# ---------------------------------------------------------------------------


def _python_files_under(dirname: str):
    root = _PKG_ROOT / dirname
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_no_production_module_references_the_mock_file():
    """Nothing in the running system may name cost_calibration_live.json.

    A status check only protects callers that look at `status`. This asserts
    the mock file has no production reader at all, which is the stronger and
    more durable guarantee -- and it catches a new loader on the day it is
    written rather than on the day its numbers reach a verdict.
    """
    offenders = [
        str(path.relative_to(_PKG_ROOT))
        for dirname in _PRODUCTION_DIRS
        for path in _python_files_under(dirname)
        if _MOCK_FILE in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        f"Production modules reference the MOCK calibration file: {offenders}. "
        "Mock costs must stay confined to the script that writes them."
    )


def test_calibration_loader_reads_only_the_measured_file():
    """dynamic_spread_model must point at cost_calibration.json, nothing else."""
    src = (_PKG_ROOT / "backtest" / "dynamic_spread_model.py").read_text(encoding="utf-8")
    literals = {
        node.value
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".json")
    }
    assert literals == {"cost_calibration.json"}, f"dynamic_spread_model.py names unexpected JSON files: {literals}"
