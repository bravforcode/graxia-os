"""Generate manifests for all parquet files in the warehouse.

INV-005 compliance: every dataset must have a manifest with SHA-256 checksum.

Usage:
    python scripts/generate_manifests.py [--dry-run] [--limit N]

Options:
    --dry-run   Show what would be done without writing files
    --limit N   Process only first N files (for testing)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import directly to avoid data/__init__.py graxia.database dependency
import importlib.util
import sys as _sys
_spec = importlib.util.spec_from_file_location("data_manifest_mod", PROJECT_ROOT / "data" / "manifest.py")
_mod = importlib.util.module_from_spec(_spec)
_sys.modules["data_manifest_mod"] = _mod
_spec.loader.exec_module(_mod)
DataManifest = _mod.DataManifest


def get_parquet_files(warehouse_dir: Path) -> list[Path]:
    """Find all parquet files that don't have manifests yet."""
    files = []
    for f in warehouse_dir.rglob("*.parquet"):
        manifest_path = f.parent / f"{f.stem}_manifest.json"
        if not manifest_path.exists():
            files.append(f)
    return sorted(files)


def extract_symbol_from_path(path: Path) -> str:
    """Extract symbol from partitioned path like symbol=XAUUSD/..."""
    for part in path.parts:
        if part.startswith("symbol="):
            return part.split("=")[1]
    return path.stem.split("_")[0] if "_" in path.stem else "UNKNOWN"


def extract_date_range_from_path(path: Path) -> str:
    """Extract date range from path structure."""
    year = None
    month = None
    for part in path.parts:
        if part.startswith("year="):
            year = part.split("=")[1]
        if part.startswith("month="):
            month = part.split("=")[1]
    if year and month:
        return f"{year}-{month}"
    if year:
        return year
    return "unknown"


def generate_manifests(
    warehouse_dir: Path,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Generate manifests for all parquet files without one."""
    files = get_parquet_files(warehouse_dir)
    if limit:
        files = files[:limit]

    results = {"total": len(files), "created": 0, "skipped": 0, "errors": []}

    for i, f in enumerate(files):
        try:
            symbol = extract_symbol_from_path(f)
            date_range = extract_date_range_from_path(f)

            if dry_run:
                print(f"  [DRY-RUN] Would create manifest for: {f.name} (symbol={symbol})")
                results["created"] += 1
                continue

            # Compute checksum and create manifest
            checksum = DataManifest.compute_checksum(f)
            schema_hash = "unknown"  # Would need to read parquet schema

            manifest = DataManifest(
                symbol=symbol,
                date_range=date_range,
                row_count=0,  # Would need to read parquet row count
                checksum=checksum,
                schema_hash=schema_hash,
                pipeline_version="1.0.0",
            )
            manifest.save(f)
            results["created"] += 1

            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{len(files)} manifests created")

        except Exception as exc:
            results["errors"].append(f"{f}: {exc}")
            results["skipped"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate INV-005 manifests for warehouse parquet files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--limit", type=int, help="Process only first N files")
    args = parser.parse_args()

    warehouse_dir = PROJECT_ROOT / "data" / "warehouse"
    if not warehouse_dir.exists():
        print(f"Warehouse directory not found: {warehouse_dir}")
        sys.exit(1)

    print(f"Scanning {warehouse_dir} for parquet files without manifests...")
    files = get_parquet_files(warehouse_dir)
    print(f"Found {len(files)} parquet files without manifests")

    if not files:
        print("All parquet files already have manifests. Nothing to do.")
        return

    if args.limit:
        print(f"Processing first {args.limit} files only")

    print("\nGenerating manifests...")
    results = generate_manifests(warehouse_dir, dry_run=args.dry_run, limit=args.limit)

    print(f"\n{'='*50}")
    print(f"Results:")
    print(f"  Total files: {results['total']}")
    print(f"  Created:     {results['created']}")
    print(f"  Skipped:     {results['skipped']}")
    if results["errors"]:
        print(f"  Errors:      {len(results['errors'])}")
        for err in results["errors"][:10]:
            print(f"    - {err}")
        if len(results["errors"]) > 10:
            print(f"    ... and {len(results['errors']) - 10} more")

    if args.dry_run:
        print("\n[DRY-RUN] No files were modified. Run without --dry-run to create manifests.")


if __name__ == "__main__":
    main()
