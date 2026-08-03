#!/usr/bin/env python3
"""
Measurement daemon runner — Phase 2 (universe cost-calibration).

Initializes one MT5 connection, symbol_select()s every symbol under
measurement (measuring/verifying by default, optional candidates), and
runs MeasurementDaemon.run_forever() so per-session-day coverage
accumulates toward the two-pass promotion bar.

State is disk-durable (data/coverage/{symbol}_coverage.json) — restarting
this script resumes coverage; it never loses day-N progress.

Usage:
    python scripts/run_measurement_daemon.py                 # measuring+verifying
    python scripts/run_measurement_daemon.py --include-candidates
    python scripts/run_measurement_daemon.py --interval 2.0
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_COVERAGE_DIR = ROOT / "data" / "coverage"
DEFAULT_TICKS_DIR = ROOT / "data" / "ticks"
UNIVERSE_PATH = ROOT / "config" / "tradeable_universe.json"

MEASUREMENT_STATUSES = ("measuring", "verifying")


def load_measurement_symbols(include_candidates: bool) -> tuple[list[str], dict[str, str]]:
    """Read the universe JSON and return (symbols, symbol_map).

    symbol_map maps universe symbol -> broker symbol (mt5_symbol field),
    so symbols like USOIL (broker name SpotCrude) fetch ticks correctly
    while coverage/parquet stay keyed by the universe symbol.
    """
    import json

    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    statuses = list(MEASUREMENT_STATUSES)
    if include_candidates:
        statuses.append("candidate")
    symbols: list[str] = []
    symbol_map: dict[str, str] = {}
    for status in statuses:
        for entry in universe.get(status, []):
            symbols.append(entry["symbol"])
            mt5_name = entry.get("mt5_symbol")
            if mt5_name and mt5_name != entry["symbol"]:
                symbol_map[entry["symbol"]] = mt5_name
    return symbols, symbol_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-symbol measurement daemon")
    parser.add_argument(
        "--include-candidates",
        action="store_true",
        help="Also measure newly discovered candidate symbols (default: measuring/verifying only)",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval seconds (default 1.0)")
    args = parser.parse_args()

    import MetaTrader5 as mt5  # noqa: N813

    from market_data.measurement_daemon import MeasurementDaemon

    if not mt5.initialize(timeout=30000):
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        raise SystemExit(1)

    symbols, symbol_map = load_measurement_symbols(args.include_candidates)
    if not symbols:
        print("No measuring/verifying/candidate symbols in universe — nothing to measure.")
        mt5.shutdown()
        raise SystemExit(0)

    for sym in symbols:
        mt5.symbol_select(symbol_map.get(sym, sym), True)

    session_id = f"daemon-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    print(f"Measuring {len(symbols)} symbols: {', '.join(symbols)}")
    print(f"Session: {session_id}")
    print(f"Coverage dir: {DEFAULT_COVERAGE_DIR}")
    print(f"Ticks dir: {DEFAULT_TICKS_DIR}")

    daemon = MeasurementDaemon(
        symbols,
        coverage_dir=DEFAULT_COVERAGE_DIR,
        ticks_dir=DEFAULT_TICKS_DIR,
        session_id=session_id,
        symbol_map=symbol_map,
    )
    try:
        daemon.run_forever(interval_seconds=args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
