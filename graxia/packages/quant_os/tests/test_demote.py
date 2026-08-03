"""Tests for market_data/demote.py (Phase 1 cost-drift demotion)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# demote.py imports core.stats.psi — the monorepo-root `core` shadows
# quant_os/core under pytest (see plan Global Constraint 2). Unconditional
# insert of the quant_os root fixes resolution order.
_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_QUANT_OS_ROOT))

import pytest  # noqa: E402

from graxia.packages.quant_os.market_data.demote import (  # noqa: E402
    COST_DRIFT_PSI_THRESHOLD,
    DemotionChecker,
    cost_drift_psi,
)
from graxia.packages.quant_os.risk.kill_switch import KillSwitch  # noqa: E402


def test_cost_drift_psi_identical_windows_is_zero():
    assert cost_drift_psi([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(0.0, abs=1e-9)


def test_cost_drift_psi_shift_is_positive():
    assert cost_drift_psi([1.0, 2.0, 3.0, 4.0, 5.0], [5.0, 6.0, 7.0, 8.0, 9.0]) > 0.1


def _fixture(tmp_path):
    universe = tmp_path / "tradeable_universe.json"
    universe.write_text(
        json.dumps(
            {
                "_meta": {"version": "1.2.0"},
                "tradeable": [{"symbol": "XAUUSD", "asset_class": "metals", "cost_status": "FROM_TICKS_MULTIDAY"}],
                "measuring": [],
                "verifying": [],
                "candidate": [],
                "excluded": [],
                "summary": {"tradeable": 1, "measuring": 0},
            }
        )
    )
    costs = tmp_path / "cost_calibration.json"
    costs.write_text(json.dumps({"version": "3.1", "assets": {"XAUUSD": {}}}))
    audit = tmp_path / "audit_log.jsonl"
    ks = KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))
    return universe, costs, audit, ks


def test_no_drift_returns_none(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe,
        cost_calibration_path=costs,
        kill_switch=ks,
        audit_log_path=audit,
    )
    # Realistic variance (degenerate constant samples hit the 1e-10 std floor
    # and explode PSI — same semantics as the shared psi() primitive).
    baseline = [1.0 + 0.1 * (i % 5) for i in range(10)]  # mean 1.2, std ~0.141
    current = [v + 0.07 for v in baseline]  # 0.5-sigma shift → PSI ~0.13 < 0.25
    result = checker.check("XAUUSD", baseline, current)
    assert result is None
    assert json.loads(universe.read_text(encoding="utf-8"))["tradeable"][0]["symbol"] == "XAUUSD"
    assert not audit.exists() or audit.read_text(encoding="utf-8").strip() == ""


def test_drift_demotes_and_flags_kill_switch(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe,
        cost_calibration_path=costs,
        kill_switch=ks,
        audit_log_path=audit,
    )
    result = checker.check("XAUUSD", [1.0] * 10, [9.0] * 10)
    assert result is not None
    assert result.previous_status == "tradeable"
    assert result.psi > COST_DRIFT_PSI_THRESHOLD

    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["tradeable"] == []
    assert uni["measuring"][0]["symbol"] == "XAUUSD"
    assert uni["measuring"][0]["demoted_reason"] == "cost_drift_psi"

    assert ks.is_symbol_killed("XAUUSD")

    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "universe.demote"
    assert record["symbol"] == "XAUUSD"
    assert record["new_status"] == "measuring"
    assert record["psi"] == pytest.approx(result.psi, abs=1e-6)


def test_insufficient_samples_returns_none(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe,
        cost_calibration_path=costs,
        kill_switch=ks,
        audit_log_path=audit,
    )
    assert checker.check("XAUUSD", [1.0, 2.0], [9.0, 10.0]) is None


def test_unknown_symbol_raises(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe,
        cost_calibration_path=costs,
        kill_switch=ks,
        audit_log_path=audit,
    )
    with pytest.raises(KeyError, match="SOLUSD"):
        checker.check("SOLUSD", [1.0] * 10, [9.0] * 10)
