"""
Standardized Manifest Generator for Quant OS

Creates INV-005 compliant SHA-256 manifests for datasets.

Usage:
    python scripts/generate_manifest.py --input data/warehouse/ticks/EURUSD/year=2024/month=01/data.parquet --manifest-dir data/manifests
    python scripts/generate_manifest.py --input data/EURUSD_M15.csv
"""

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST_DIR = os.path.join(PROJECT_ROOT, "data", "manifests")


def _compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of raw file bytes."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_schema_hash(columns: List[str]) -> str:
    """Compute a deterministic hash of column names."""
    canonical = json.dumps(sorted(columns), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _extract_symbol(filepath: str) -> str:
    """Extract symbol from path heuristically."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    base_upper = basename.upper()

    known = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "GBPJPY", "AUDUSD", "USDCAD", "NZDUSD"]
    for sym in known:
        if sym in base_upper or sym in basename:
            return sym
    parts = basename.split("_")
    if parts and len(parts[0]) == 6:
        return parts[0]
    return basename


def _extract_timeframe(filepath: str) -> Optional[str]:
    """Extract timeframe from path or filename."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    parts = basename.upper().split("_")
    for p in parts:
        if p in timeframes:
            return p
    for tf in timeframes:
        if tf in basename.upper():
            return tf
    return None


def _extract_source(filepath: str, manifest_dir: Optional[str] = None) -> str:
    """Extract data source from path or existing manifest."""
    path_upper = filepath.upper()
    if "MT5" in path_upper:
        return "MT5"
    if "DUKASCOPY" in path_upper:
        return "Dukascopy"
    if "YAHOO" in path_upper or "YFINANCE" in path_upper:
        return "Yahoo"
    # Check existing manifest for source info
    if manifest_dir and os.path.isdir(manifest_dir):
        basename = os.path.splitext(os.path.basename(filepath))[0]
        for suffix in [".manifest.json", "_manifest.json"]:
            m_path = os.path.join(manifest_dir, f"{basename}{suffix}")
            if os.path.exists(m_path):
                try:
                    with open(m_path) as f:
                        return json.load(f).get("source", "unknown")
                except Exception:
                    pass
    return "unknown"


def _read_metadata(filepath: str) -> Tuple[Optional[int], Optional[List[str]], Optional[str], Optional[str]]:
    """Read row count, columns, min timestamp, max timestamp from file."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".parquet":
        try:
            import pandas as pd
            df = pd.read_parquet(filepath)
            rows = len(df)
            columns = list(df.columns)
            ts_col = _find_timestamp_col(columns)
            start_ts = None
            end_ts = None
            if ts_col and rows > 0:
                try:
                    start_ts = str(df[ts_col].iloc[0])
                    end_ts = str(df[ts_col].iloc[-1])
                except Exception:
                    pass
            return rows, columns, start_ts, end_ts
        except ImportError:
            pass

        try:
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(filepath)
            rows = pf.metadata.num_rows
            columns = pf.schema_arrow.names
            return rows, columns, None, None
        except ImportError:
            print("ERROR: No parquet reader available. Install pandas or pyarrow.")
            return None, None, None, None

    elif ext == ".csv":
        try:
            with open(filepath, "r", newline="") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames
                rows = 0
                first_ts = None
                last_ts = None
                ts_col = _find_timestamp_col(columns) if columns else None

                for row in reader:
                    rows += 1
                    if ts_col and first_ts is None:
                        first_ts = row.get(ts_col)
                    if ts_col:
                        last_ts = row.get(ts_col)

                return rows, columns, first_ts, last_ts
        except Exception as e:
            print(f"ERROR reading CSV: {e}")
            return None, None, None, None

    else:
        print(f"ERROR: Unsupported format: {ext}")
        return None, None, None, None


def _find_timestamp_col(columns: List[str]) -> Optional[str]:
    """Find the timestamp column from a list."""
    for col in columns:
        col_lower = col.lower().strip()
        if col_lower in ("timestamp", "time", "datetime", "date", "ts"):
            return col
    return None


def generate_manifest(
    filepath: str,
    manifest_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an INV-005 compliant manifest for the given file.

    Args:
        filepath: Path to the data file (parquet or csv).
        manifest_dir: Directory to write the manifest file. If None, prints to stdout.

    Returns:
        dict with manifest contents (also written to disk if manifest_dir is set).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath}")

    absolute_path = os.path.abspath(filepath)
    sha256_hash = _compute_sha256(absolute_path)

    rows, columns, start_ts, end_ts = _read_metadata(absolute_path)
    if columns is None:
        raise RuntimeError(f"Could not read metadata from: {filepath}")

    symbol = _extract_symbol(filepath)
    timeframe = _extract_timeframe(filepath)
    source = _extract_source(filepath, manifest_dir)
    schema_hash = _compute_schema_hash(columns)

    manifest: Dict[str, Any] = {
        "sha256": sha256_hash,
        "file_path": absolute_path,
        "rows": rows or 0,
        "columns": columns,
        "symbol": symbol,
        "schema_hash": schema_hash,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if start_ts and end_ts:
        manifest["date_range"] = {
            "start": start_ts,
            "end": end_ts,
        }

    if timeframe:
        manifest["timeframe"] = timeframe

    if source != "unknown":
        manifest["source"] = source

    if symbol and timeframe and source:
        clean_source = source.replace("/", "_").replace(" ", "_")
        manifest["dataset_id"] = f"{symbol}_{timeframe}_{clean_source}_{rows}"

    if manifest_dir:
        os.makedirs(manifest_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(filepath))[0]
        manifest_path = os.path.join(manifest_dir, f"{basename}_manifest.json")

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"Manifest written to: {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Generate INV-005 compliant SHA-256 manifest for a dataset"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to input data file (.parquet or .csv)",
    )
    parser.add_argument(
        "--manifest-dir", "-d", default=None,
        help="Directory to write manifest file (default: data/manifests/)",
    )
    args = parser.parse_args()

    manifest_dir = args.manifest_dir
    if manifest_dir is None:
        manifest_dir = DEFAULT_MANIFEST_DIR

    manifest = generate_manifest(args.input, manifest_dir)

    print("\nManifest summary:")
    print(f"  File:     {manifest['file_path']}")
    print(f"  SHA-256:  {manifest['sha256'][:16]}...")
    print(f"  Rows:     {manifest['rows']}")
    print(f"  Columns:  {len(manifest['columns'])}")
    print(f"  Schema:   {manifest['schema_hash'][:16]}...")
    if "date_range" in manifest:
        print(f"  Period:   {manifest['date_range']['start']} -> {manifest['date_range']['end']}")


if __name__ == "__main__":
    main()
