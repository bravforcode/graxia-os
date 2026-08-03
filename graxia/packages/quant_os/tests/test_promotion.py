"""Tests for market_data/promotion.py (Phase 1 promotion bar enforcer)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_data.promotion import compute_cost_stats, promote_symbol
from market_data.tick_recorder import TickRecorder


def _records(n: int):
    recs = []
    for i in range(n):
        recs.append(
            TickRecorder("XAUUSD", "s1").record_tick(
                bid=Decimal("2300.00"),
                ask=Decimal("2300.20"),
                last=Decimal("2300.10"),
                timestamp_utc=datetime(2026, 8, 3, 12, i % 60, 0, tzinfo=UTC),
            )
        )
    return recs


def _fixture(tmp_path):
    universe = tmp_path / "tradeable_universe.json"
    universe.write_text(
        json.dumps(
            {
                "_meta": {"version": "1.2.0"},
                "tradeable": [],
                "measuring": [{"symbol": "XAUUSD", "asset_class": "metals"}],
                "verifying": [],
                "candidate": [],
                "excluded": [],
                "summary": {"tradeable": 0, "measuring": 1, "verifying": 0},
            }
        )
    )
    costs = tmp_path / "cost_calibration.json"
    costs.write_text(json.dumps({"version": "3.1", "assets": {}}))
    audit = tmp_path / "audit_log.jsonl"
    evidence = tmp_path / "XAUUSD_2026-08-03.parquet"
    evidence.write_bytes(b"parquet-evidence")
    return universe, costs, audit, evidence


def test_compute_cost_stats_median_p95():
    stats = compute_cost_stats(_records(100))
    assert stats["status"] == "FROM_TICKS_MULTIDAY"
    assert stats["sample_size"] == 100
    assert stats["spread_bps_measured"] == pytest.approx(0.8696, abs=1e-3)


def test_compute_cost_stats_requires_samples():
    with pytest.raises(ValueError, match="at least 2"):
        compute_cost_stats(_records(1))


def test_promote_measuring_to_verifying(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    result = promote_symbol(
        "XAUUSD",
        pass_index=1,
        records=_records(100),
        parquet_files=[evidence],
        mt5_symbol="XAUUSD",
        measurement_window="2026-08-03 to 2026-08-10 (7 qualifying days)",
        universe_path=universe,
        cost_calibration_path=costs,
        audit_log_path=audit,
    )
    assert result["new_status"] == "verifying"
    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["verifying"][0]["symbol"] == "XAUUSD"
    assert uni["measuring"] == []
    assert json.loads(costs.read_text(encoding="utf-8"))["assets"]["XAUUSD"]["status"] == "FROM_TICKS_MULTIDAY"
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "universe.promote"
    assert json.loads(lines[0])["symbol"] == "XAUUSD"


def test_promote_verifying_to_tradeable(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    uni = json.loads(universe.read_text(encoding="utf-8"))
    uni["verifying"] = uni["measuring"]
    uni["measuring"] = []
    universe.write_text(json.dumps(uni))

    result = promote_symbol(
        "XAUUSD",
        pass_index=2,
        records=_records(100),
        parquet_files=[evidence],
        mt5_symbol="XAUUSD",
        measurement_window="2026-08-13 to 2026-08-20 (7 qualifying days)",
        universe_path=universe,
        cost_calibration_path=costs,
        audit_log_path=audit,
    )
    assert result["new_status"] == "tradeable"
    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["tradeable"][0]["symbol"] == "XAUUSD"
    assert uni["verifying"] == []


def test_promote_fails_closed_on_missing_evidence(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    missing = tmp_path / "XAUUSD_2026-08-04.parquet"
    with pytest.raises(FileNotFoundError, match="promotion evidence missing"):
        promote_symbol(
            "XAUUSD",
            pass_index=1,
            records=_records(100),
            parquet_files=[missing],
            mt5_symbol="XAUUSD",
            measurement_window="w",
            universe_path=universe,
            cost_calibration_path=costs,
            audit_log_path=audit,
        )
    # Nothing written on failure:
    assert json.loads(costs.read_text(encoding="utf-8"))["assets"] == {}
