#!/usr/bin/env python3
"""
Phase 3 — Multi-Instrument Selection Layer (driver).

Reads the Phase 2C cost-verified universe (config/tradeable_universe.json),
runs each candidate through the canonical walk-forward engine with real
costs (reusing scripts/run_multi_instrument_wf.py's load_data/run_wf_single,
not duplicating them), applies Benjamini-Hochberg correction across the
batch (validation.instrument_selection.select_instruments), and writes the
result to config/selected_instruments.json -- the file run_paper_trading.py
reads to decide which symbols it's allowed to trade.

Every audit doc in this repo agrees there is no confirmed edge yet. This
script is honest about that: it may select zero instruments, and that is
the correct result, not a failure of the script.

Usage:
    python scripts/select_tradeable_instruments.py
    python scripts/select_tradeable_instruments.py --dry-run
    python scripts/select_tradeable_instruments.py --timeframe H1 --alpha 0.05
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
# validation/__init__.py imports native_runner.py, which needs the
# graxia.packages.quant_os.* dotted path -- only resolvable with the
# monorepo root on sys.path (same requirement run_multi_instrument_wf.py
# already has, just never exercised standalone before).
sys.path.insert(0, str(BASE.parent.parent.parent))

from run_multi_instrument_wf import load_data, run_wf_single  # noqa: E402

from validation.instrument_selection import select_instruments  # noqa: E402

UNIVERSE_PATH = BASE / "config" / "tradeable_universe.json"
COST_CALIBRATION_PATH = BASE / "config" / "cost_calibration.json"
OUTPUT_PATH = BASE / "config" / "selected_instruments.json"

# tradeable_universe.json's symbol name -> cost_calibration.json asset key,
# only where they differ (see tradeable_universe.json's USOIL note: "Maps
# to MT5 symbol: OIL").
_COST_KEY_OVERRIDES = {"USOIL": "OIL"}


def _load_candidates() -> list[str]:
    if not UNIVERSE_PATH.exists():
        raise SystemExit(f"ERROR: {UNIVERSE_PATH} not found -- run Phase 2C first.")
    universe = json.loads(UNIVERSE_PATH.read_text())
    return [entry["symbol"] for entry in universe.get("tradeable", [])]


def _cost_lookup_fn(costs_raw: dict):
    def _lookup(symbol: str) -> dict | None:
        cost_key = _COST_KEY_OVERRIDES.get(symbol, symbol)
        asset = costs_raw.get("assets", {}).get(cost_key)
        if not asset:
            return None
        rt_bps = asset.get("round_trip_bps_measured", 0)
        if rt_bps <= 0:
            return None
        per_trade_return = (rt_bps / 2.0) / 10000.0
        return {"spread": per_trade_return * 0.5, "slippage": per_trade_return * 0.5}

    return _lookup


def _load_ohlcv_fn(timeframe: str, data_dir: Path):
    def _loader(symbol: str):
        loader_symbol = _COST_KEY_OVERRIDES.get(symbol, symbol)
        return load_data(loader_symbol, timeframe, data_dir)

    return _loader


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 instrument selection")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--data-dir", default=str(BASE / "data"))
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the result without writing selected_instruments.json"
    )
    args = parser.parse_args()

    candidates = _load_candidates()
    if not COST_CALIBRATION_PATH.exists():
        raise SystemExit(f"ERROR: {COST_CALIBRATION_PATH} not found.")
    costs_raw = json.loads(COST_CALIBRATION_PATH.read_text())

    print(f"Candidates (cost-verified universe): {candidates}")

    result = select_instruments(
        candidates,
        load_ohlcv_fn=_load_ohlcv_fn(args.timeframe, Path(args.data_dir)),
        cost_lookup_fn=_cost_lookup_fn(costs_raw),
        run_wf_fn=run_wf_single,
        timeframe=args.timeframe,
        alpha=args.alpha,
        min_trades=args.min_trades,
    )

    for e in result.evaluations:
        print(
            f"  {e.symbol:10s} status={e.status:16s} t={e.t_stat:+6.2f} "
            f"folds={e.n_folds:3d} trades={e.total_trades:5d} "
            f"raw_p={e.raw_p_value:.4f} adj_p={e.adjusted_p_value:.4f} "
            f"stable={e.stable} SELECTED={e.selected}"
        )

    print(f"\nSelected: {result.selected_symbols or '(none)'}")

    payload = {
        "_meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "alpha": result.alpha,
            "min_trades": result.min_trades,
            "candidates_source": str(UNIVERSE_PATH.relative_to(BASE)),
            "method": (
                "walk-forward fold t-statistic -> two-sided p-value -> "
                "Benjamini-Hochberg FDR correction across the batch "
                "(validation.multiple_testing.benjamini_hochberg), not a "
                "naive per-instrument threshold"
            ),
        },
        "selected": result.selected_symbols,
        "evaluations": [
            {
                "symbol": e.symbol,
                "status": e.status,
                "t_statistic": e.t_stat,
                "n_folds": e.n_folds,
                "total_trades": e.total_trades,
                "raw_p_value": e.raw_p_value,
                "adjusted_p_value": e.adjusted_p_value,
                "stable": e.stable,
                "selected": e.selected,
            }
            for e in result.evaluations
        ],
    }

    if args.dry_run:
        print(f"\n--dry-run: not writing {OUTPUT_PATH}")
        return

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
