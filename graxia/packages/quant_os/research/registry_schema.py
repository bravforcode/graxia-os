"""Trial entry schema + provenance stamping (Phase 1, Unit U1).

Every trial verdict written to research/hypothesis_registry*.json must carry
cost provenance: which cost_calibration.json version, which symbols' spread /
commission / slippage values were used, and where slippage came from. This
module is the single place that builds + validates those fields so no future
trial can silently run on guessed/fabricated costs (the 33b90c31 class of bug).

Usage (trial runners):
    from research.registry_schema import stamp_trial_entry, validate_trial_entry

    entry = stamp_trial_entry(
        trial_number=8001,
        id="DIRG-BTC-DONCHIAN-H1",
        status="REJECTED",
        instrument="BTCUSD (H1)",
        symbols=["BTCUSD"],
        cost_model_version="4.1",
        cost_source="FROM_TICKS",
        round_trip_bps_used={"BTCUSD": 14.752},
        slippage_source="fill_simulator_p90_points",
        slippage_bps_used={"BTCUSD": 32.0},  # points, fill P90
        data_manifest_ref=None,
        result_summary={...},
    )
    validate_trial_entry(entry)   # raises ValueError on missing provenance

Design notes:
- Append-only: never delete a provenance field once written.
- FAIL-CLOSED: validate_trial_entry raises if a trial claiming a non-null
  result lacks cost_model_version / cost_source / round_trip_bps_used.
- Slippage is allowed to be null ONLY when slippage_source is "none" (honest
  "we did not model it") — never a fabricated 0.0.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Required provenance keys for any entry with a non-null result.
_REQUIRED_PROVENANCE = (
    "cost_model_version",
    "cost_source",
    "round_trip_bps_used",
    "slippage_source",
)

VALID_COST_SOURCES = {"FROM_TICKS", "SINGLE_SNAPSHOT", "MOCK", "UNVERIFIED_NO_DATA", "none"}
VALID_SLIPPAGE_SOURCES = {"fill_simulator_p90_points", "none"}

REQUIRED_ENTRY_FIELDS = (
    "trial_number",
    "id",
    "status",
    "instrument",
    "result_summary",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stamp_trial_entry(
    *,
    trial_number: int,
    id: str,
    status: str,
    instrument: str,
    symbols: list[str],
    cost_model_version: str,
    cost_source: str,
    round_trip_bps_used: dict[str, float],
    slippage_source: str,
    slippage_bps_used: dict[str, float] | None = None,
    data_manifest_ref: str | None = None,
    result_summary: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict:
    """Build a registry entry with full cost provenance, ready to append."""
    entry: dict[str, Any] = {
        "trial_number": trial_number,
        "id": id,
        "status": status,
        "instrument": instrument,
        "symbols": symbols,
        "registered_at": _now_iso(),
        "result_at": _now_iso() if status != "PRE_REGISTERED" else None,
        "result_summary": result_summary or {},
        # ---- provenance block ----
        "cost_model_version": cost_model_version,
        "cost_source": cost_source,
        "round_trip_bps_used": round_trip_bps_used,
        "slippage_source": slippage_source,
        "slippage_bps_used": slippage_bps_used,
        "data_manifest_ref": data_manifest_ref,
        "provenance_stamped_at": _now_iso(),
    }
    if notes:
        entry["notes"] = notes
    validate_trial_entry(entry)
    return entry


def validate_trial_entry(entry: dict) -> None:
    """FAIL-CLOSED validation of a registry entry's provenance.

    Raises ValueError on: missing required fields, unknown cost/slippage
    sources, or (for non-null results) missing provenance.
    """
    missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in entry]
    if missing:
        raise ValueError(f"entry missing required fields: {missing}")

    has_result = entry.get("status") != "PRE_REGISTERED" and bool(entry.get("result_summary"))
    if has_result:
        missing_prov = [f for f in _REQUIRED_PROVENANCE if entry.get(f) in (None, "", {})]
        if missing_prov:
            raise ValueError(
                f"trial #{entry['trial_number']} ({entry.get('id')}) has a result but is missing "
                f"provenance: {missing_prov}. Refusing to accept unprovenanced verdict."
            )

    cost_source = entry.get("cost_source")
    if cost_source not in VALID_COST_SOURCES:
        raise ValueError(f"unknown cost_source: {cost_source!r}")

    slip_src = entry.get("slippage_source")
    if slip_src not in VALID_SLIPPAGE_SOURCES:
        raise ValueError(f"unknown slippage_source: {slip_src!r}")

    if slip_src == "none" and entry.get("slippage_bps_used") not in (None, {}):
        raise ValueError("slippage_source='none' but slippage_bps_used is set — inconsistent")
    if slip_src == "fill_simulator_p90_points" and not entry.get("slippage_bps_used"):
        raise ValueError(
            "slippage_source='fill_simulator_p90_points' but slippage_bps_used missing — "
            "refusing to fake 0.0 slippage"
        )


def load_registry(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_entry(registry_path: str | Path, entry: dict) -> None:
    """Append a stamped entry to a registry file (atomic, newline-terminated)."""
    import os
    import tempfile

    path = Path(registry_path)
    registry = load_registry(path)
    registry.setdefault("hypotheses", []).append(entry)
    registry["last_updated"] = _now_iso()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".reg_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(path))
