#!/usr/bin/env python3
"""Resumable multi-source historical backfill CLI."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.backfill import dukascopy, mt5_history  # noqa: E402
from data_pipeline.backfill.binance import fetch_funding, fetch_trades  # noqa: E402

# `data` is not importable as a top-level package (data/__init__.py uses
# `..core.enums`) — same importlib file-load pattern as
# scripts/generate_manifests.py and market_data/measurement_daemon.py.
_manifest_spec = importlib.util.spec_from_file_location("data_manifest_mod", ROOT / "data" / "manifest.py")
assert _manifest_spec is not None and _manifest_spec.loader is not None
_data_manifest_mod = importlib.util.module_from_spec(_manifest_spec)
sys.modules["data_manifest_mod"] = _data_manifest_mod  # dataclass machinery needs it
_manifest_spec.loader.exec_module(_data_manifest_mod)
DataManifestManager = _data_manifest_mod.DataManifestManager

DEFAULT_OUT = ROOT / "data" / "backfill"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical tick backfill (idempotent, resumable)")
    parser.add_argument("--source", required=True, choices=["binance", "dukascopy", "mt5"])
    parser.add_argument("--dataset", required=True, choices=["funding", "trades", "ticks"])
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--symbols", default="", help="comma-separated (default: all configured)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def run_one_source(
    source: str,
    dataset: str,
    start: str,
    end: str,
    symbols: list[str],
    out_dir: Path,
    manifest_dir: str | Path | None = None,
) -> int:
    out = Path(out_dir) / f"{source}_{dataset}"
    total = 0
    for sym in symbols:
        if source == "binance" and dataset == "funding":
            paths = fetch_funding(sym, start, end, out)
        elif source == "binance" and dataset == "trades":
            paths = fetch_trades(sym, start, end, out)
        elif source == "dukascopy":
            paths = dukascopy.fetch_ticks(sym, start, end, out)
        elif source == "mt5":
            from_msc = int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp() * 1000)
            to_msc = int(datetime.fromisoformat(end).replace(tzinfo=UTC).timestamp() * 1000)
            paths = mt5_history.fetch_ticks(sym, from_msc, to_msc, out)
        else:
            raise ValueError(f"unsupported source/dataset: {source}/{dataset}")
        total += len(paths)
        print(f"  {sym}: {len(paths)} parquet files")
    DataManifestManager(manifest_dir).update_manifest(dataset, sorted(out.glob("*.parquet")))
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print(f"Backfilling {args.source}/{args.dataset} {args.start}..{args.end} for {symbols}")
    total = run_one_source(args.source, args.dataset, args.start, args.end, symbols, Path(args.out_dir))
    print(f"Done: {total} parquet files written (resumable — rerun to continue).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
