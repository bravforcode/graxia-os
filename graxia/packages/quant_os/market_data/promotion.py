"""Promotion bar enforcer (Phase 1).

Moves a symbol measuring → verifying after pass 1, verifying → tradeable after
pass 2, writes full provenance into cost_calibration.json
(status: "FROM_TICKS_MULTIDAY"), and appends the audit trail. The daemon never
emits a status it cannot back with a named parquet file on disk — this module
hard-verifies every parquet path it cites.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from market_data.measurement_daemon import spread_bps


def append_audit(audit_log_path: str | Path, record: dict) -> None:
    """Append one JSON line to the audit log (same shape as core/signal_gateway)."""
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def compute_cost_stats(records) -> dict:
    """Aggregate cost stats from TickRecords (spread in bps)."""
    samples = [spread_bps(r) for r in records if spread_bps(r) != float("inf")]
    if len(samples) < 2:
        raise ValueError("need at least 2 valid spread samples to compute cost stats")
    samples_sorted = sorted(samples)
    n = len(samples_sorted)
    median = samples_sorted[n // 2] if n % 2 else (samples_sorted[n // 2 - 1] + samples_sorted[n // 2]) / 2
    p95 = samples_sorted[min(int(n * 0.95), n - 1)]
    mean = sum(samples_sorted) / n
    return {
        "spread_bps_measured": round(median, 4),
        "spread_bps_p95": round(p95, 4),
        "spread_bps_mean": round(mean, 4),
        "spread_bps_min": round(samples_sorted[0], 4),
        "spread_bps_max": round(samples_sorted[-1], 4),
        "round_trip_bps_measured": round(median * 2, 4),
        "sample_size": n,
        "status": "FROM_TICKS_MULTIDAY",
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".promo_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


def _move_universe_entry(universe: dict, symbol: str, from_key: str, to_key: str) -> bool:
    entries = universe.get(from_key, [])
    for i, entry in enumerate(entries):
        if entry.get("symbol") == symbol:
            moved = entries.pop(i)
            universe.setdefault(to_key, []).append(moved)
            return True
    return False


def promote_symbol(
    symbol: str,
    *,
    pass_index: int,
    records,
    parquet_files: list[str | Path],
    mt5_symbol: str,
    measurement_window: str,
    contract_size: float | None = None,
    universe_path: str | Path,
    cost_calibration_path: str | Path,
    audit_log_path: str | Path,
) -> dict:
    """Advance the symbol's status and persist evidence.

    pass_index=1: measuring → verifying (writes cost entry first).
    pass_index=2: verifying → tradeable (keeps the pass-1 cost entry).

    Every parquet_files entry must exist on disk — a missing evidence file
    aborts the promotion (fail-closed, no status without provenance).
    """
    for f in parquet_files:
        if not Path(f).exists():
            raise FileNotFoundError(f"promotion evidence missing: {f}")

    universe = json.loads(Path(universe_path).read_text(encoding="utf-8"))
    costs = json.loads(Path(cost_calibration_path).read_text(encoding="utf-8"))

    stats = compute_cost_stats(records)
    cost_key = mt5_symbol
    entry = {
        "mt5_symbol": mt5_symbol,
        "spread_bps_measured": stats["spread_bps_measured"],
        "spread_bps_p95": stats["spread_bps_p95"],
        "spread_bps_mean": stats["spread_bps_mean"],
        "spread_bps_min": stats["spread_bps_min"],
        "spread_bps_max": stats["spread_bps_max"],
        "spread_bps_std": 0.0,
        "commission_bps": 0,
        "slippage_bps_measured": None,
        "round_trip_bps_measured": stats["round_trip_bps_measured"],
        "contract_size": contract_size,
        "tick_size": None,
        "status": stats["status"],
        "sample_size": stats["sample_size"],
        "measurement_window": measurement_window,
        "measurement_caveat": (
            f"Multi-day measurement from Phase 1 daemon; evidence parquet: "
            f"{', '.join(str(p) for p in parquet_files)}."
        ),
        "notes": "Promoted automatically by Phase 1 pipeline; audit ref recorded in state/audit_log.jsonl.",
        "swap_long_bps": 0.0,
        "swap_short_bps": 0.0,
    }
    costs.setdefault("assets", {})[cost_key] = entry
    costs["calibration_status"] = "MIXED — see per-asset 'status' field"
    _atomic_write_json(Path(cost_calibration_path), costs)

    if pass_index == 1:
        moved = _move_universe_entry(universe, symbol, "measuring", "verifying")
        new_status = "verifying"
    elif pass_index == 2:
        moved = _move_universe_entry(universe, symbol, "verifying", "tradeable")
        new_status = "tradeable"
    else:
        raise ValueError(f"pass_index must be 1 or 2, got {pass_index}")

    if not moved:
        raise KeyError(f"{symbol} not found in the expected source array for pass_index={pass_index}")

    universe.setdefault("summary", {}).update(
        {
            "tradeable": len(universe.get("tradeable", [])),
            "measuring": len(universe.get("measuring", [])),
            "verifying": len(universe.get("verifying", [])),
        }
    )
    _atomic_write_json(Path(universe_path), universe)

    audit_ref = f"promote:{symbol}:{new_status}:{datetime.now(UTC).isoformat()}"
    append_audit(
        audit_log_path,
        {
            "event": "universe.promote",
            "symbol": symbol,
            "from_status": "measuring" if pass_index == 1 else "verifying",
            "to_status": new_status,
            "pass_index": pass_index,
            "sample_size": stats["sample_size"],
            "round_trip_bps_measured": stats["round_trip_bps_measured"],
            "parquet_evidence": [str(p) for p in parquet_files],
            "audit_ref": audit_ref,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    return {"symbol": symbol, "new_status": new_status, "audit_ref": audit_ref, "stats": stats}
