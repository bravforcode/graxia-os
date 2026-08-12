"""
Convert CSV files to Parquet in-place.

Scans directories for CSV files and converts each to .parquet,
reporting compression ratios. Removes the original CSV on success.

Usage:
    python scripts/convert_to_parquet.py [--dir artifacts/mega_data]
"""
import argparse
import os
import sys
from glob import glob

try:
    import pyarrow.csv as pa_csv
    import pyarrow.parquet as pq

    PYARROW_OK = True
except ImportError:
    pa_csv = pq = None
    PYARROW_OK = False


def get_csv_size(path: str) -> int:
    return os.path.getsize(path)


def csv_to_parquet(csv_path: str) -> tuple:
    table = pa_csv.read_csv(csv_path)
    parquet_path = csv_path.rsplit(".", 1)[0] + ".parquet"
    pq.write_table(table, parquet_path)
    csv_size = get_csv_size(csv_path)
    parquet_size = get_csv_size(parquet_path)
    ratio = csv_size / parquet_size if parquet_size else 0
    os.remove(csv_path)
    return parquet_path, csv_size, parquet_size, ratio


def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to Parquet in-place")
    parser.add_argument(
        "--dir", type=str, default="artifacts",
        help="Base directory to scan for CSV files (default: artifacts)",
    )
    args = parser.parse_args()

    if not PYARROW_OK:
        print("pyarrow is not installed. Install with: pip install pyarrow", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.dir):
        print(f"Directory not found: {args.dir}", file=sys.stderr)
        sys.exit(1)

    # Collect all CSV files in target subdirectories
    patterns = [
        os.path.join(args.dir, "tick_data", "*.csv"),
        os.path.join(args.dir, "mega_data", "orders", "*.csv"),
        os.path.join(args.dir, "batch_orders", "*.csv"),
    ]
    csv_files = []
    for p in patterns:
        csv_files.extend(glob(p))

    if not csv_files:
        print(f"No CSV files found under {args.dir}/[tick_data, mega_data/orders, batch_orders]")
        return

    total_csv = 0
    total_parquet = 0
    converted = 0
    errors = 0

    for csv_path in sorted(csv_files):
        try:
            parquet_path, csv_size, parquet_size, ratio = csv_to_parquet(csv_path)
            total_csv += csv_size
            total_parquet += parquet_size
            converted += 1
            print(f"  {csv_path}")
            print(f"    CSV: {csv_size:>10,} B -> Parquet: {parquet_size:>10,} B ({ratio:.2f}x compression)")
        except Exception as e:
            errors += 1
            print(f"  ERROR: {csv_path} - {e}", file=sys.stderr)

    overall = total_csv / total_parquet if total_parquet else 0
    print(f"\nConverted {converted} file(s), {errors} error(s)")
    print(f"Total: {total_csv:,} B CSV -> {total_parquet:,} B Parquet ({overall:.2f}x compression)")


if __name__ == "__main__":
    main()
