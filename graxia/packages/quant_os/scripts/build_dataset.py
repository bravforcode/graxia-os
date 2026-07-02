"""
DATA PIPELINE - Merge tick data + order execution records for training.

Reads tick CSVs and batch order CSVs, computes features, outputs training dataset.
Supports CSV and Parquet output via --format.

Usage:
    python scripts/build_dataset.py [--tick-dir artifacts/tick_data] [--batch-dir artifacts/batch_orders] [--format csv|parquet]
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, UTC
from glob import glob

try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    PYARROW_OK = True
except ImportError:
    pa = pq = None
    PYARROW_OK = False

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "training_dataset")


def load_ticks(tick_dir):
    """Load all tick CSVs into list of dicts."""
    ticks = []
    for filepath in sorted(glob(os.path.join(tick_dir, "*_ticks_*.csv"))):
        symbol = os.path.basename(filepath).split("_ticks_")[0]
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["symbol"] = symbol
                row["bid"] = float(row["bid"])
                row["ask"] = float(row["ask"])
                row["last"] = float(row["last"])
                row["spread_points"] = float(row["spread_points"])
                row["spread_price"] = float(row["spread_price"])
                row["volume"] = int(row["volume"])
                ticks.append(row)
    return ticks


def load_orders(batch_dir):
    """Load all batch order CSVs into list of dicts."""
    orders = []
    for filepath in sorted(glob(os.path.join(batch_dir, "batch_*.csv"))):
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for key in ["entry_planned", "entry_actual", "sl", "tp", "buffer", "slippage_points"]:
                    if row.get(key):
                        try:
                            row[key] = float(row[key])
                        except ValueError:
                            row[key] = None
                for key in ["send_retcode", "close_retcode", "send_deal", "close_deal", "volume"]:
                    if row.get(key):
                        try:
                            row[key] = int(row[key]) if row[key].isdigit() else row[key]
                        except (ValueError, AttributeError):
                            pass
                orders.append(row)
    return orders


def compute_features(ticks, orders):
    """Compute training features from tick + order data."""
    features = []

    # Group ticks by symbol
    ticks_by_symbol = {}
    for t in ticks:
        sym = t["symbol"]
        if sym not in ticks_by_symbol:
            ticks_by_symbol[sym] = []
        ticks_by_symbol[sym].append(t)

    # For each order, find surrounding ticks
    for order in orders:
        sym = order["symbol"]
        send_time = order.get("send_time", "")
        if not send_time or sym not in ticks_by_symbol:
            continue

        # Find ticks within 5 seconds of order
        surrounding = []
        for t in ticks_by_symbol[sym]:
            if t["timestamp_utc"][:19] == send_time[:19]:
                surrounding.append(t)

        if not surrounding:
            continue

        # Compute features
        bids = [t["bid"] for t in surrounding]
        asks = [t["ask"] for t in surrounding]
        spreads = [t["spread_price"] for t in surrounding]

        feature = {
            "order_id": order["order_id"],
            "symbol": sym,
            "side": order["side"],
            "volume": order["volume"],
            "entry_planned": order.get("entry_planned"),
            "entry_actual": order.get("entry_actual"),
            "sl": order.get("sl"),
            "tp": order.get("tp"),
            "slippage_points": order.get("slippage_points"),
            "send_retcode": order.get("send_retcode"),
            "close_retcode": order.get("close_retcode"),
            "status": order.get("status"),
            # Tick features
            "tick_count": len(surrounding),
            "bid_mean": round(sum(bids) / len(bids), 5) if bids else None,
            "bid_min": min(bids) if bids else None,
            "bid_max": max(bids) if bids else None,
            "ask_mean": round(sum(asks) / len(asks), 5) if asks else None,
            "ask_min": min(asks) if asks else None,
            "ask_max": max(asks) if asks else None,
            "spread_mean": round(sum(spreads) / len(spreads), 5) if spreads else None,
            "spread_max": max(spreads) if spreads else None,
            "bid_ask_range": round(max(asks) - min(bids), 5) if bids and asks else None,
            "send_time": send_time,
        }
        features.append(feature)

    return features


def _check_pyarrow(required: bool = False):
    if not PYARROW_OK:
        msg = "pyarrow is not installed. Install with: pip install pyarrow"
        if required:
            print(msg, file=sys.stderr)
            sys.exit(1)
        print(msg)


def main():
    parser = argparse.ArgumentParser(description="Build training dataset")
    parser.add_argument("--tick-dir", type=str, default=os.path.join("artifacts", "tick_data"))
    parser.add_argument("--batch-dir", type=str, default=os.path.join("artifacts", "batch_orders"))
    parser.add_argument(
        "--format", type=str, default="csv", choices=["csv", "parquet"],
        help="Output format (csv or parquet, default: csv). Requires pyarrow for parquet.",
    )
    args = parser.parse_args()

    if args.format == "parquet":
        _check_pyarrow(required=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Loading ticks from {args.tick_dir}...")
    ticks = load_ticks(args.tick_dir)
    print(f"  Loaded {len(ticks)} ticks")

    print(f"Loading orders from {args.batch_dir}...")
    orders = load_orders(args.batch_dir)
    print(f"  Loaded {len(orders)} orders")

    print("Computing features...")
    features = compute_features(ticks, orders)
    print(f"  Generated {len(features)} feature rows")

    # Write training dataset
    if features:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if args.format == "parquet":
            table = pa.Table.from_pylist(features)
            out_path = os.path.join(OUTPUT_DIR, f"training_{timestamp}.parquet")
            pq.write_table(table, out_path)
            print(f"  Parquet: {out_path}")
        else:
            out_path = os.path.join(OUTPUT_DIR, f"training_{timestamp}.csv")
            with open(out_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=features[0].keys())
                writer.writeheader()
                writer.writerows(features)
            print(f"  CSV: {out_path}")

    # Write summary
    symbols = set(f["symbol"] for f in features)
    sides = {"BUY": 0, "SELL": 0}
    statuses = {}
    for f in features:
        sides[f["side"]] = sides.get(f["side"], 0) + 1
        statuses[f["status"]] = statuses.get(f["status"], 0) + 1

    summary = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "total_ticks": len(ticks),
        "total_orders": len(orders),
        "total_features": len(features),
        "symbols": list(symbols),
        "side_distribution": sides,
        "status_distribution": statuses,
    }

    summary_path = os.path.join(OUTPUT_DIR, "dataset_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDataset built: {len(features)} rows from {len(ticks)} ticks + {len(orders)} orders")
    print(f"Symbols: {symbols}")
    print(f"Side dist: {sides}")
    print(f"Status dist: {statuses}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
