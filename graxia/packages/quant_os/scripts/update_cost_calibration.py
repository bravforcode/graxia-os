"""Cost Calibration Update — Merge measured spreads into cost_calibration_live.json.

Reads the spread measurement summary (from measure_spread_continuous.py) and
updates the cost calibration JSON with measured per-session, per-symbol values.

Usage:
    # From spread measurement summary:
    python scripts/update_cost_calibration.py \
        --from-spread-data data/spread_measurements/spread_summary.json \
        --output config/cost_calibration_live.json

    # Merge with existing calibration (preserves non-spread fields):
    python scripts/update_cost_calibration.py \
        --from-spread-data data/spread_measurements/spread_summary.json \
        --merge-with config/cost_calibration.json \
        --output config/cost_calibration_live.json

Output:
    JSON with updated calibration including measured spreads per session.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Contract specs (for reference in output)
# ---------------------------------------------------------------------------
CONTRACT_SPECS = {
    "XAUUSD": {"contract_size": 100, "tick_size": 0.01},
    "XAGUSD": {"contract_size": 5000, "tick_size": 0.001},
    "EURUSD": {"contract_size": 100000, "tick_size": 0.00001},
    "GBPUSD": {"contract_size": 100000, "tick_size": 0.00001},
    "USDJPY": {"contract_size": 100000, "tick_size": 0.001},
    "NAS100": {"contract_size": 1, "tick_size": 0.01},
    "US30":   {"contract_size": 1, "tick_size": 0.01},
    "OIL":    {"contract_size": 1000, "tick_size": 0.001},
    "USOIL":  {"contract_size": 1000, "tick_size": 0.001},
}

COMMISSION_BPS = {
    "XAUUSD": 0, "XAGUSD": 0,  # Metals: $0 commission (Pepperstone Razor)
    "EURUSD": 7, "GBPUSD": 7, "USDJPY": 7,  # FX: $7/rt
    "NAS100": 0, "US30": 0,  # Indices: $0
    "OIL": 0, "USOIL": 0,  # Energy: $0
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file with UTF-8 encoding."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_spread_summary(path: Path) -> dict[str, Any]:
    """Load spread measurement summary and validate structure."""
    data = _load_json(path)

    if "symbols" not in data:
        raise ValueError(
            f"Invalid spread summary: missing 'symbols' key. "
            f"Keys: {list(data.keys())}"
        )

    return data


# ---------------------------------------------------------------------------
# Calibration computation
# ---------------------------------------------------------------------------


def _compute_session_averages(
    spread_summary: dict[str, Any],
) -> dict[str, dict[str, dict[str, float]]]:
    """Compute average spread per session per symbol.

    Returns: {symbol: {session: {spread_bps_median, spread_bps_p95, ...}}}
    """
    result: dict[str, dict[str, dict[str, float]]] = {}

    symbols_data = spread_summary.get("symbols", {})
    for symbol, data in symbols_data.items():
        sessions = data.get("sessions", {})
        result[symbol] = {}

        for session_name, stats in sessions.items():
            if stats.get("count", 0) == 0:
                continue
            result[symbol][session_name] = {
                "spread_bps_median": stats.get("median", 0.0),
                "spread_bps_p95": stats.get("p95", 0.0),
                "spread_bps_min": stats.get("min", 0.0),
                "spread_bps_max": stats.get("max", 0.0),
                "spread_bps_p25": stats.get("p25", 0.0),
                "spread_bps_p75": stats.get("p75", 0.0),
                "sample_count": stats.get("count", 0),
            }

    return result


def _build_calibration_entry(
    symbol: str,
    session_averages: dict[str, dict[str, float]],
    overall: dict[str, float],
    measurement_meta: dict[str, Any],
) -> dict[str, Any]:
    """Build a single symbol's calibration entry."""
    # Compute weighted average across sessions (by sample count)
    total_samples = sum(s.get("sample_count", 0) for s in session_averages.values())
    if total_samples > 0:
        weighted_median = sum(
            s["spread_bps_median"] * s["sample_count"]
            for s in session_averages.values()
        ) / total_samples
        weighted_p95 = sum(
            s["spread_bps_p95"] * s["sample_count"]
            for s in session_averages.values()
        ) / total_samples
    else:
        weighted_median = 0.0
        weighted_p95 = 0.0

    specs = CONTRACT_SPECS.get(symbol, {"contract_size": 1, "tick_size": 0.01})
    commission = COMMISSION_BPS.get(symbol, 0)

    entry: dict[str, Any] = {
        "mt5_symbol": symbol,
        "spread_bps_measured": round(weighted_median, 4),
        "spread_bps_p95": round(weighted_p95, 4),
        "spread_bps_mean": round(overall.get("median", 0.0), 4),
        "spread_bps_min": round(overall.get("min", 0.0), 4),
        "spread_bps_max": round(overall.get("max", 0.0), 4),
        "spread_bps_std": round(
            (overall.get("p75", 0) - overall.get("p25", 0)) / 1.35, 4
        ),  # IQR-based std estimate
        "commission_bps": commission,
        "slippage_bps_measured": round(weighted_median * 0.5, 4),  # Estimate: 50% of spread
        "round_trip_bps_measured": round(weighted_median * 2 + commission, 4),
        "round_trip_bps_p95": round(weighted_p95 * 2 + commission, 4),
        "contract_size": specs["contract_size"],
        "tick_size": specs["tick_size"],
        "status": "MEASURED",
        "sample_size": total_samples,
        "measurement_window": measurement_meta.get("timestamp", "unknown"),
        "measurement_duration_days": measurement_meta.get("duration_days", 0),
        "measurement_mode": measurement_meta.get("mode", "unknown"),
        "sessions": session_averages,
    }

    return entry


def build_calibration(
    spread_summary: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build updated cost calibration from spread measurement data.

    Parameters
    ----------
    spread_summary : dict
        Output from measure_spread_continuous.py.
    existing : dict | None
        Existing calibration to merge with (preserves non-spread fields).

    Returns
    -------
    dict with updated calibration.
    """
    meta = spread_summary.get("metadata", {})
    session_avgs = _compute_session_averages(spread_summary)

    # Start from existing or create new
    calibration: dict[str, Any] = {
        "version": "4.0",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Measured via measure_spread_continuous.py",
        "note": "Auto-generated from continuous spread measurement. Per-session statistics included.",
    }

    # Preserve fields from existing calibration
    if existing:
        for key in ("swap_rate_note", "stress_scenarios", "removed_assets"):
            if key in existing and key not in calibration:
                calibration[key] = existing[key]

    # Build per-asset entries
    assets: dict[str, Any] = {}
    symbols_data = spread_summary.get("symbols", {})

    for symbol, data in symbols_data.items():
        overall = data.get("overall", {})
        sessions = session_avgs.get(symbol, {})
        entry = _build_calibration_entry(symbol, sessions, overall, meta)

        # Merge with existing entry if present
        if existing and "assets" in existing and symbol in existing["assets"]:
            old = existing["assets"][symbol]
            # Preserve fields not measured (swap rates, notes)
            for preserve_key in ("swap_long_bps", "swap_short_bps", "notes"):
                if preserve_key in old and preserve_key not in entry:
                    entry[preserve_key] = old[preserve_key]

        assets[symbol] = entry

    # Merge existing assets not in current measurement
    if existing and "assets" in existing:
        for symbol, old_entry in existing["assets"].items():
            if symbol not in assets:
                old_entry["status"] = "STALE"
                old_entry["notes"] = old_entry.get("notes", "") + " (not re-measured)"
                assets[symbol] = old_entry

    calibration["assets"] = assets
    calibration["calibration_status"] = "MEASURED"
    calibration["measurement_total_samples"] = sum(
        d.get("overall", {}).get("count", 0)
        for d in symbols_data.values()
    )
    calibration["measurement_asset_count"] = len(assets)
    calibration["measurement_metadata"] = meta

    return calibration


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _write_calibration(calibration: dict[str, Any], output_path: Path) -> None:
    """Write calibration JSON with UTF-8 encoding."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, default=str)


def _print_summary(calibration: dict[str, Any]) -> None:
    """Print a human-readable summary of the calibration."""
    print("=" * 60)
    print("  COST CALIBRATION UPDATE")
    print("=" * 60)
    print(f"  Version:  {calibration.get('version', '?')}")
    print(f"  Date:     {calibration.get('date', '?')}")
    print(f"  Status:   {calibration.get('calibration_status', '?')}")
    print(f"  Assets:   {calibration.get('measurement_asset_count', 0)}")
    print(f"  Samples:  {calibration.get('measurement_total_samples', 0)}")
    print("-" * 60)

    assets = calibration.get("assets", {})
    for symbol, data in assets.items():
        status = data.get("status", "?")
        median = data.get("spread_bps_measured", 0)
        p95 = data.get("spread_bps_p95", 0)
        rt = data.get("round_trip_bps_measured", 0)
        print(f"  {symbol:>8s}  median={median:.4f}  p95={p95:.4f}  "
              f"RT={rt:.4f} bps  [{status}]")

        sessions = data.get("sessions", {})
        for sess_name, sess_data in sessions.items():
            s_median = sess_data.get("spread_bps_median", 0)
            s_p95 = sess_data.get("spread_bps_p95", 0)
            s_n = sess_data.get("sample_count", 0)
            print(f"    {sess_name:>8s}:  median={s_median:.4f}  p95={s_p95:.4f}  n={s_n}")

    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update cost calibration from measured spread data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/update_cost_calibration.py \\
      --from-spread-data data/spread_measurements/spread_summary.json \\
      --output config/cost_calibration_live.json

  python scripts/update_cost_calibration.py \\
      --from-spread-data data/spread_measurements/spread_summary.json \\
      --merge-with config/cost_calibration.json \\
      --output config/cost_calibration_live.json
        """,
    )
    parser.add_argument(
        "--from-spread-data",
        type=str,
        required=True,
        help="Path to spread measurement summary JSON (from measure_spread_continuous.py).",
    )
    parser.add_argument(
        "--merge-with",
        type=str,
        default=None,
        help="Path to existing calibration JSON to merge with (preserves non-spread fields).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "config" / "cost_calibration_live.json"),
        help=f"Output JSON path (default: config/cost_calibration_live.json).",
    )

    args = parser.parse_args()

    spread_path = Path(args.from_spread_data)
    output_path = Path(args.output)

    try:
        spread_summary = _load_spread_summary(spread_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid spread data: {e}", file=sys.stderr)
        sys.exit(2)

    existing = None
    if args.merge_with:
        try:
            existing = _load_json(Path(args.merge_with))
        except FileNotFoundError as e:
            print(f"WARNING: {e} — starting fresh.", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"WARNING: Invalid existing calibration: {e} — starting fresh.",
                  file=sys.stderr)

    try:
        calibration = build_calibration(spread_summary, existing)
    except Exception as e:
        print(f"ERROR: Failed to build calibration: {e}", file=sys.stderr)
        sys.exit(2)

    _write_calibration(calibration, output_path)
    _print_summary(calibration)

    print(f"\n  Output: {output_path}")


if __name__ == "__main__":
    main()
