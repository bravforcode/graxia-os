"""
SPREAD ANALYSIS — Reads data/spread_log.jsonl, computes per-asset statistics.

Outputs:
    data/spread_analysis.json  — per-asset median, P95, sample count
    config/cost_calibration.json — updated with MEASURED values

Usage:
    python scripts/analyze_spread.py [--input data/spread_log.jsonl] [--update-config]
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = BASE / "data" / "spread_log.jsonl"
ANALYSIS_OUTPUT = BASE / "data" / "spread_analysis.json"
CONFIG_OUTPUT = BASE / "config" / "cost_calibration.json"

# Pepperstone Razor commission: $7/rt on FX, $0 on metals/crypto
COMMISSION_BPS = {
    "XAUUSD": 0,
    "EURUSD": 7,
    "GBPUSD": 7,
    "USDJPY": 7,
    "BTCUSD": 0,
    "ETHUSD": 0,
    "XAGUSD": 0,
    "SpotCrude": 0,
}

# Contract sizes for bps→dollar conversion context
CONTRACT_SIZE = {
    "XAUUSD": 100,
    "EURUSD": 100000,
    "GBPUSD": 100000,
    "USDJPY": 100000,
    "BTCUSD": 1,
    "ETHUSD": 1,
    "XAGUSD": 5000,
    "SpotCrude": 1000,
}

TICK_SIZE = {
    "XAUUSD": 0.01,
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
    "BTCUSD": 0.01,
    "ETHUSD": 0.01,
    "XAGUSD": 0.001,
    "SpotCrude": 0.001,
}

NOTES = {
    "XAUUSD": "Pepperstone Razor: $0 commission on metals",
    "EURUSD": "Pepperstone Razor: $7/rt commission on FX",
    "GBPUSD": "Pepperstone Razor: $7/rt commission on FX",
    "USDJPY": "Pepperstone Razor: $7/rt commission on FX",
    "BTCUSD": "Pepperstone CFD: $0 commission on crypto",
    "ETHUSD": "Pepperstone CFD: $0 commission on crypto",
    "XAGUSD": "Pepperstone Razor: $0 commission on metals (SILVER)",
    "SpotCrude": "Pepperstone CFD: $0 commission on energy (OIL/WTI)",
}

# Display name mapping for reports
DISPLAY_NAMES = {
    "XAGUSD": "SILVER",
    "SpotCrude": "OIL",
}


def load_log(path: Path) -> list[dict]:
    """Load all samples from JSONL file."""
    if not path.exists():
        print(f"[FATAL] Input file not found: {path}")
        sys.exit(1)

    samples = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping line {i}: {e}")
    return samples


def compute_stats(samples: list[dict]) -> dict:
    """Compute per-asset statistics from spread samples."""
    by_symbol: dict[str, list[float]] = {}
    timestamps: dict[str, list[str]] = {}

    for s in samples:
        sym = s.get("symbol")
        bps = s.get("spread_bps")
        if sym and bps is not None:
            by_symbol.setdefault(sym, []).append(float(bps))
            timestamps.setdefault(sym, []).append(s.get("timestamp", ""))

    results = {}
    for sym, bps_list in by_symbol.items():
        arr = np.array(bps_list)
        ts_list = timestamps.get(sym, [])
        window_start = min(ts_list) if ts_list else "unknown"
        window_end = max(ts_list) if ts_list else "unknown"

        results[sym] = {
            "spread_bps_median": round(float(np.median(arr)), 2),
            "spread_bps_p95": round(float(np.percentile(arr, 95)), 2),
            "spread_bps_mean": round(float(np.mean(arr)), 2),
            "spread_bps_min": round(float(np.min(arr)), 2),
            "spread_bps_max": round(float(np.max(arr)), 2),
            "spread_bps_std": round(float(np.std(arr)), 2),
            "sample_count": len(arr),
            "measurement_window_start": window_start,
            "measurement_window_end": window_end,
        }

    return results


def build_calibration(stats: dict) -> dict:
    """Build new cost_calibration.json from measured stats."""
    assets = {}
    for sym in sorted(stats.keys()):
        s = stats[sym]
        commission = COMMISSION_BPS.get(sym, 0)
        median = s["spread_bps_median"]
        p95 = s["spread_bps_p95"]
        display = DISPLAY_NAMES.get(sym, sym)

        assets[display] = {
            "mt5_symbol": sym,
            "spread_bps_measured": median,
            "spread_bps_p95": p95,
            "spread_bps_mean": s["spread_bps_mean"],
            "spread_bps_min": s["spread_bps_min"],
            "spread_bps_max": s["spread_bps_max"],
            "spread_bps_std": s["spread_bps_std"],
            "commission_bps": commission,
            "slippage_bps_measured": None,
            "round_trip_bps_measured": round(median * 2 + commission, 2),
            "round_trip_bps_p95": round(p95 * 2 + commission, 2),
            "contract_size": CONTRACT_SIZE.get(sym, 0),
            "tick_size": TICK_SIZE.get(sym, 0),
            "status": "MEASURED",
            "sample_size": s["sample_count"],
            "measurement_window": f"{s['measurement_window_start'][:10]} to {s['measurement_window_end'][:10]}",
            "notes": NOTES.get(sym, ""),
        }

    # Preserve stress scenarios from original if exists
    stress = {}
    if CONFIG_OUTPUT.exists():
        try:
            with open(CONFIG_OUTPUT) as f:
                old = json.load(f)
                stress = old.get("stress_scenarios", {})
        except Exception:
            pass

    now = datetime.now(UTC).strftime("%Y-%m-%d")
    total_samples = sum(s["sample_count"] for s in stats.values())

    return {
        "version": "2.0",
        "date": now,
        "source": "Pepperstone Razor account — MEASURED",
        "note": f"Real spread measurement from {total_samples} samples across {len(assets)} assets.",
        "assets": assets,
        "stress_scenarios": stress,
        "calibration_status": "MEASURED",
        "measurement_total_samples": total_samples,
        "measurement_asset_count": len(assets),
    }


def print_report(stats: dict) -> None:
    """Print human-readable summary."""
    print("\n" + "=" * 70)
    print("SPREAD MEASUREMENT REPORT")
    print("=" * 70)

    header = f"{'Symbol':<12} {'Median':>8} {'P95':>8} {'Mean':>8} {'Min':>8} {'Max':>8} {'N':>6}"
    print(header)
    print("-" * 70)

    for sym in sorted(stats.keys()):
        s = stats[sym]
        display = DISPLAY_NAMES.get(sym, sym)
        print(
            f"{display:<12} {s['spread_bps_median']:>8.2f} {s['spread_bps_p95']:>8.2f} "
            f"{s['spread_bps_mean']:>8.2f} {s['spread_bps_min']:>8.2f} {s['spread_bps_max']:>8.2f} "
            f"{s['sample_count']:>6}"
        )

    print("-" * 70)

    # Alert check
    print("\nALERT CHECK:")
    for sym in sorted(stats.keys()):
        s = stats[sym]
        display = DISPLAY_NAMES.get(sym, sym)
        median = s["spread_bps_median"]
        p95 = s["spread_bps_p95"]
        is_fx = sym in ("EURUSD", "GBPUSD", "USDJPY")
        is_crypto = sym in ("BTCUSD", "ETHUSD")
        threshold = 50 if is_fx else (100 if is_crypto else 80)

        if p95 > threshold:
            print(f"  [ALERT] {display}: P95={p95:.1f} bps > {threshold} bps threshold")
        else:
            print(f"  [OK]    {display}: P95={p95:.1f} bps (threshold={threshold})")

    total = sum(s["sample_count"] for s in stats.values())
    min_samples = min(s["sample_count"] for s in stats.values())
    print(f"\nTotal samples: {total}")
    print(f"Min per-asset samples: {min_samples}")

    if min_samples < 10:
        print("[WARN] Need at least 10 samples per asset for reliable calibration.")
    if min_samples < 10080:  # 1 week at 1/min
        print("[INFO] Full calibration needs ~10080 samples/asset (1 week @ 1/min).")
        print(f"[INFO] Current min: {min_samples}. Continue logging for better accuracy.")


def main():
    parser = argparse.ArgumentParser(description="Analyze spread log and update cost calibration")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="Path to spread_log.jsonl")
    parser.add_argument(
        "--update-config", action="store_true", default=True, help="Update cost_calibration.json (default: True)"
    )
    parser.add_argument("--no-update", action="store_true", help="Skip config update, only produce analysis")
    args = parser.parse_args()

    input_path = Path(args.input)
    print(f"[LOAD] Reading {input_path}...")
    samples = load_log(input_path)
    print(f"[LOAD] {len(samples)} samples loaded.")

    if not samples:
        print("[FATAL] No samples found. Run measure_spread.py first.")
        sys.exit(1)

    stats = compute_stats(samples)
    if not stats:
        print("[FATAL] No valid symbol data found.")
        sys.exit(1)

    # Save analysis
    ANALYSIS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(ANALYSIS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"[SAVE] Analysis written to {ANALYSIS_OUTPUT}")

    # Update config
    if args.update_config and not args.no_update:
        calibration = build_calibration(stats)
        CONFIG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(calibration, f, indent=2)
        print(f"[SAVE] Calibration written to {CONFIG_OUTPUT}")

    print_report(stats)


if __name__ == "__main__":
    main()
