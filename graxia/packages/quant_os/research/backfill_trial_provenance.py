"""Backfill cost provenance for trials 1034/1035 (Phase 1, Unit U4).

Reads reports/edge_search_m15_scalper_core4.json (the runner artifact for
EA-BENCH trials 1034/1035) plus config/cost_calibration.json and stamps each
registry entry with the provenance fields that were missing at registration
time (cost_model_version, cost_source, round_trip_bps_used, slippage_source).

Where the artifact does not record a cost source explicitly, we infer from the
runner's frozen config (BacktestEngine measured-cost path -> cost_calibration.json
values) and mark provenance as INFERRED_FROM_ARTIFACT — never as if it had been
measured at registration time. Append-only: adds fields, changes nothing else.

Usage:
    python research/backfill_trial_provenance.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "research" / "hypothesis_registry.json"
ARTIFACT_PATH = ROOT / "reports" / "edge_search_m15_scalper_core4.json"
COST_PATH = ROOT / "config" / "cost_calibration.json"

TRIALS = (1034, 1035)


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".reg_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(path))


def main() -> int:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    cost = json.loads(COST_PATH.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))

    # Which symbols each trial touched (from artifact per_asset for 1035, and
    # the trial's own instrument field otherwise).
    per_asset = artifact.get("per_asset", {})

    stamped = 0
    for entry in registry.get("hypotheses", []):
        tn = entry.get("trial_number")
        if tn not in TRIALS:
            continue
        if entry.get("cost_model_version") and entry.get("cost_source"):
            print(f"trial {tn}: already stamped — skip")
            continue

        symbols = []
        if isinstance(entry.get("symbols"), list):
            symbols = entry["symbols"]
        elif isinstance(entry.get("instrument"), str):
            # extract tokens from "XAUUSD (M15)" or "MULTI-ASSET 3-SYM (EURUSD, GBPUSD, USDJPY)"
            import re

            candidates = re.findall(r"[A-Z]{4,6}", entry["instrument"])
            # Keep only tokens that exist in cost_calibration (real symbols,
            # not descriptive words like "MULTI"/"ASSET"/"SYM").
            symbols = [c for c in candidates if c in cost.get("assets", {})]
        if not symbols:
            symbols = list(per_asset.keys())

        rt_bps = {}
        cost_sources = set()
        for sym in symbols:
            cal = cost.get("assets", {}).get(sym, {})
            status = cal.get("status", "UNKNOWN")
            cost_sources.add(status)
            spread = float(cal.get("spread_bps_measured", 0.0) or 0.0)
            comm = float(cal.get("commission_bps", 0.0) or 0.0)
            rt_bps[sym] = round(spread * 2 + comm * 2, 4)

        entry["cost_model_version"] = str(cost.get("version", "UNKNOWN"))
        entry["cost_source"] = "/".join(sorted(cost_sources)) or "UNKNOWN"
        entry["round_trip_bps_used"] = rt_bps
        entry["slippage_source"] = "none"  # runner had no slippage model (slippage_pips=None)
        entry["slippage_bps_used"] = None
        entry["provenance_backfilled_at"] = None  # filled below
        entry["provenance_note"] = (
            "INFERRED_FROM_ARTIFACT 2026-08-05: runner artifact "
            "(reports/edge_search_m15_scalper_core4.json) records BacktestEngine "
            "measured-cost path with slippage_pips=None; cost values taken from "
            "config/cost_calibration.json per-symbol entries. NOT re-measured — "
            "backfilled for audit completeness."
        )
        stamped += 1
        print(f"trial {tn} ({entry.get('id')}): symbols={symbols} rt_bps={rt_bps} source={entry['cost_source']}")

    if stamped:
        _atomic_write_json(REGISTRY_PATH, registry)
        print(f"\nBackfilled provenance for {stamped} trial(s) in {REGISTRY_PATH.name}")
    else:
        print("No trials needed backfill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
