"""Populate manifest system for all parquet files in data/warehouse/.

Generates:
- DuckDB manifests table rows (INSERT OR REPLACE)
- JSON sidecar files in data/warehouse/manifests/

Re-runnable (idempotent).

Usage:
    python scripts/warehouse/populate_manifests.py
    python scripts/warehouse/populate_manifests.py --dry-run
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pyarrow.parquet as pq


# ======================================================================
# Config
# ======================================================================

DB_PATH = Path("data/warehouse/quantos.duckdb")
MANIFESTS_DIR = Path("data/warehouse/manifests")
WAREHOUSE_ROOT = Path("data/warehouse")
MAX_WORKERS = 8
BATCH_SIZE = 500  # DuckDB insert batch size


# ======================================================================
# Manifest computation
# ======================================================================


def compute_file_hash(file_path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_partition_info(file_path: Path) -> dict[str, str]:
    """Extract symbol, frequency/source, timeframe from Hive partition path.

    OHLCV path: data/warehouse/ohlcv/symbol=XAUUSD/frequency=D1/source=MT5/year=2024/month=01/file.parquet
    Ticks path:  data/warehouse/ticks/source=MT5/symbol=XAUUSD/year=2026/month=06/file.parquet
    """
    rel = file_path.relative_to(WAREHOUSE_ROOT)
    parts = {}
    for part in rel.parts:
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k] = v

    symbol = parts.get("symbol", "UNKNOWN")
    source = parts.get("source", "UNKNOWN")
    timeframe = parts.get("frequency")  # ohlcv uses 'frequency', ticks has none
    return {"symbol": symbol, "source": source, "timeframe": timeframe or ""}


def compute_parquet_manifest(file_path: Path) -> dict:
    """Compute manifest dict for a single parquet file."""
    pf = pq.ParquetFile(file_path)
    schema = pf.schema_arrow
    num_rows = pf.metadata.num_rows
    columns = [f.name for f in schema]
    col_types = {f.name: str(f.type) for f in schema}

    # Date range from time column if available
    try:
        table = pf.read(columns=["time"]) if "time" in columns else None
        if table and len(table) > 0:
            times = table.column("time").to_pylist()
            valid_times = [t for t in times if t is not None]
            date_start = min(valid_times).isoformat() if valid_times else None
            date_end = max(valid_times).isoformat() if valid_times else None
        else:
            date_start = None
            date_end = None
    except Exception:
        date_start = None
        date_end = None

    partition_info = parse_partition_info(file_path)
    file_size = file_path.stat().st_size
    checksum = compute_file_hash(file_path)

    return {
        "sha256": checksum,
        "rows": num_rows,
        "columns": json.dumps(columns),
        "date_start": date_start,
        "date_end": date_end,
        "symbol": partition_info["symbol"],
        "source": partition_info["source"],
        "timeframe": partition_info["timeframe"],
        "file_path": str(file_path).replace("\\", "/"),
        "file_size": file_size,
        "created_at": date.today().isoformat(),
        # Extra fields for JSON sidecar
        "col_types": col_types,
        "schema_hash": hashlib.sha256(
            json.dumps({"columns": columns, "dtypes": col_types}, sort_keys=True).encode()
        ).hexdigest()[:16],
    }


# ======================================================================
# Sidecar JSON writer
# ======================================================================


def write_sidecar_json(manifest: dict, manifests_dir: Path) -> Path:
    """Write manifest JSON sidecar file."""
    manifests_dir.mkdir(parents=True, exist_ok=True)
    file_path = Path(manifest["file_path"])
    stem = file_path.stem
    # Create a unique name using the parent directory structure
    rel = file_path.relative_to(WAREHOUSE_ROOT)
    safe_name = str(rel).replace("/", "_").replace("\\", "_").replace(".parquet", "")
    sidecar_path = manifests_dir / f"{safe_name}_manifest.json"

    sidecar_data = {
        "sha256": manifest["sha256"],
        "rows": manifest["rows"],
        "columns": json.loads(manifest["columns"]) if isinstance(manifest["columns"], str) else manifest["columns"],
        "date_start": manifest["date_start"],
        "date_end": manifest["date_end"],
        "symbol": manifest["symbol"],
        "source": manifest["source"],
        "timeframe": manifest["timeframe"],
        "file_path": manifest["file_path"],
        "file_size": manifest["file_size"],
        "created_at": manifest["created_at"],
        "schema_hash": manifest.get("schema_hash", ""),
    }
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2, default=str))
    return sidecar_path


# ======================================================================
# Symlink helpers
# ======================================================================


def ensure_symlinks() -> None:
    """Create symlinks for Bronze/Silver/Gold structure."""
    links = [
        ("data/warehouse/bronze/ohlcv", "data/warehouse/ohlcv"),
        ("data/warehouse/bronze/ticks", "data/warehouse/ticks"),
        ("data/warehouse/bronze/manifests", "data/warehouse/manifests"),
        ("data/warehouse/silver/ohlcv", "data/warehouse/ohlcv"),
        ("data/warehouse/silver/manifests", "data/warehouse/manifests"),
        ("data/warehouse/gold/ohlcv", "data/warehouse/ohlcv"),
    ]
    for link_path, target_path in links:
        link = Path(link_path)
        target = Path(target_path)
        if link.exists() or link.is_symlink():
            continue  # already exists
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Use absolute paths for Windows compatibility
            link.symlink_to(target.resolve(), target_is_directory=True)
            print(f"  symlink: {link_path} -> {target_path}")
        except OSError:
            # On Windows, symlinks may require admin. Use directory junction instead.
            import subprocess
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target.resolve())],
                check=True, capture_output=True,
            )
            print(f"  junction: {link_path} -> {target_path}")


# ======================================================================
# Main pipeline
# ======================================================================


def collect_parquet_files() -> list[Path]:
    """Find all parquet files in ohlcv/ and ticks/."""
    files = []
    for subdir in ("ohlcv", "ticks"):
        base = WAREHOUSE_ROOT / subdir
        if base.exists():
            files.extend(base.rglob("*.parquet"))
    return sorted(files)


def process_file(file_path: Path) -> dict | None:
    """Process a single parquet file. Returns manifest dict or None on error."""
    try:
        return compute_parquet_manifest(file_path)
    except Exception as exc:
        print(f"  ERROR processing {file_path}: {exc}", file=sys.stderr)
        return None


def populate_manifests(dry_run: bool = False) -> dict:
    """Main entry point: populate manifests for all parquet files.

    Returns:
        Dict with counts: {'files': N, 'manifests_inserted': N, 'sidecars_written': N, 'errors': N}
    """
    files = collect_parquet_files()
    total = len(files)
    print(f"Found {total} parquet files to process")

    if total == 0:
        return {"files": 0, "manifests_inserted": 0, "sidecars_written": 0, "errors": 0}

    # Phase 1: Compute all manifests in parallel
    print(f"Phase 1: Computing manifests ({MAX_WORKERS} workers)...")
    manifests = []
    errors = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process_file, f): f for f in files}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                manifests.append(result)
            else:
                errors += 1
            if i % 500 == 0 or i == total:
                print(f"  [{i}/{total}] processed ({time.time()-t0:.1f}s)")

    print(f"Phase 1 complete: {len(manifests)} manifests, {errors} errors, {time.time()-t0:.1f}s")

    if dry_run:
        print("DRY RUN — skipping writes")
        return {"files": total, "manifests_inserted": 0, "sidecars_written": 0, "errors": errors}

    # Phase 2: Write to DuckDB
    print("Phase 2: Writing to DuckDB manifests table...")
    con = duckdb.connect(str(DB_PATH))
    con.execute("DELETE FROM manifests")  # idempotent: clear existing

    for i in range(0, len(manifests), BATCH_SIZE):
        batch = manifests[i:i + BATCH_SIZE]
        con.executemany(
            """INSERT INTO manifests
               (sha256, rows, columns, date_start, date_end, symbol, source, timeframe, file_path, file_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(m["sha256"], m["rows"], m["columns"], m["date_start"], m["date_end"],
              m["symbol"], m["source"], m["timeframe"], m["file_path"], m["file_size"], m["created_at"])
             for m in batch],
        )
        print(f"  [{min(i+BATCH_SIZE, len(manifests))}/{len(manifests)}] DuckDB rows inserted")

    duckdb_count = con.execute("SELECT count(*) FROM manifests").fetchone()[0]
    con.close()
    print(f"DuckDB manifests: {duckdb_count} rows")

    # Phase 3: Write JSON sidecars
    print("Phase 3: Writing JSON sidecar files...")
    sidecars = 0
    for m in manifests:
        write_sidecar_json(m, MANIFESTS_DIR)
        sidecars += 1
    print(f"Sidecars written: {sidecars}")

    # Phase 4: Create symlinks
    print("Phase 4: Creating Bronze/Silver/Gold symlinks...")
    ensure_symlinks()

    return {
        "files": total,
        "manifests_inserted": duckdb_count,
        "sidecars_written": sidecars,
        "errors": errors,
    }


# ======================================================================
# CLI
# ======================================================================


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN MODE ===\n")

    result = populate_manifests(dry_run=dry_run)

    print("\n=== SUMMARY ===")
    for k, v in result.items():
        print(f"  {k}: {v}")

    if result["errors"] > 0:
        print(f"\nWARNING: {result['errors']} files failed to process")
        sys.exit(1)


if __name__ == "__main__":
    main()
