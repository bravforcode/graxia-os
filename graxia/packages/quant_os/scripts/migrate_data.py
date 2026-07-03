"""
Migrate legacy data formats to standardized warehouse Parquet.

Converts OHLCV CSVs, tick parquets, bulk tick CSVs, and fill sample
CSVs into Hive-style partitioned Parquet under data/warehouse/,
following the schema defined in docs/schema.md.

Usage:
    python scripts/migrate_data.py --types ohlcv,ticks,fills
    python scripts/migrate_data.py --types ohlcv --dry-run
    python scripts/migrate_data.py --types ticks --force --validate
"""

import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("migrate_data")

WAREHOUSE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "ohlcv": {
        "time": pa.timestamp("us"),
        "open": pa.float64(),
        "high": pa.float64(),
        "low": pa.float64(),
        "close": pa.float64(),
        "volume": pa.int64(),
        "frequency": pa.utf8(),
        "symbol": pa.utf8(),
        "source": pa.utf8(),
    },
    "ticks": {
        "time": pa.timestamp("us"),
        "bid": pa.float64(),
        "ask": pa.float64(),
        "last": pa.float64(),
        "flags": pa.int32(),
        "volume": pa.float64(),
        "ask_volume": pa.float64(),
        "spread": pa.float64(),
        "source": pa.utf8(),
        "symbol": pa.utf8(),
    },
    "fill_samples": {
        "time": pa.timestamp("us"),
        "symbol": pa.utf8(),
        "side": pa.utf8(),
        "volume": pa.float64(),
        "simulation_id": pa.utf8(),
        "fill_price": pa.float64(),
        "requested_price": pa.float64(),
        "slippage_points": pa.float64(),
        "spread_at_fill": pa.float64(),
        "latency_model": pa.utf8(),
        "tick_sequence_index": pa.int64(),
        "sigma_slippage": pa.float64(),
    },
}

PARTITION_KEYS: Dict[str, List[str]] = {
    "ohlcv": ["symbol", "frequency", "source", "year", "month"],
    "ticks": ["source", "symbol", "year", "month"],
    "fill_samples": ["symbol", "simulation_id", "year", "month"],
}

WAREHOUSE_SUBDIRS: Dict[str, str] = {
    "ohlcv": "ohlcv",
    "ticks": "ticks",
    "fill_samples": "fill_samples",
}


def _parse_ts(val: Any) -> Optional[pd.Timestamp]:
    if isinstance(val, pd.Timestamp):
        return val
    if isinstance(val, datetime):
        return pd.Timestamp(val)
    if isinstance(val, (int, float)):
        return pd.Timestamp(val, unit="s")
    if isinstance(val, str):
        val = val.strip()
        try:
            return pd.Timestamp(val)
        except (ValueError, TypeError):
            pass
        try:
            return pd.Timestamp(val, unit="s")
        except (ValueError, TypeError):
            pass
    return None


def _parse_symbol_tf(filename: str) -> Tuple[str, str]:
    stem = Path(filename).stem
    match = re.match(r"([A-Z]+)_([A-Z0-9]+)$", stem)
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"Cannot parse symbol and timeframe from filename: {filename}")


def _parse_symbol_bulk(filename: str) -> str:
    stem = Path(filename).stem
    symbol = stem.split("_bulk")[0]
    return symbol.upper()


def _parse_symbol_ticks(filename: str) -> str:
    stem = Path(filename).stem
    symbol = stem.split("_ticks")[0]
    return symbol.upper()


def _build_schema(columns: Dict[str, Any]) -> pa.Schema:
    return pa.schema([pa.field(k, v) for k, v in columns.items()])


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_partitioned(
    df: pd.DataFrame,
    table_type: str,
    target_dir: Path,
    partition_cols: List[str],
    force: bool,
    dry_run: bool,
) -> Tuple[int, int]:
    has_time_partition = "year" in partition_cols and "month" in partition_cols

    if "time" in df.columns:
        df = df.sort_values("time").reset_index(drop=True)

    schema = _build_schema(WAREHOUSE_SCHEMAS[table_type])
    data_cols = list(WAREHOUSE_SCHEMAS[table_type].keys())

    data_df = df[data_cols].copy()
    table = pa.Table.from_pandas(data_df, preserve_index=False)
    table = table.cast(schema, safe=False)

    if has_time_partition:
        year = df["time"].dt.year.astype(str)
        month = df["time"].dt.month.astype(str).str.zfill(2)
        table = table.append_column("year", pa.array(year))
        table = table.append_column("month", pa.array(month))

    if table_type == "ticks" or table_type == "fill_samples":
        table = table.sort_by([("time", "ascending")])

    partition_cols_present = [c for c in partition_cols if c in table.schema.names]

    if dry_run:
        total_rows = len(df)
        return total_rows, 0

    temp_dir = Path(tempfile.mkdtemp(dir=target_dir.parent))

    moved = []
    try:
        pq.write_to_dataset(
            table,
            root_path=str(temp_dir / table_type),
            partition_cols=partition_cols_present,
            compression="zstd",
            row_group_size=65536,
        )

        for path in temp_dir.rglob("*.parquet"):
            rel_path = path.relative_to(temp_dir / table_type)
            target_path = target_dir / rel_path
            _ensure_dir(target_path.parent)

            if target_path.exists() and not force:
                log.warning("  Target exists, skipping: %s", target_path)
                path.unlink()
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target_path))
            moved.append(target_path)

        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    total_size = sum(f.stat().st_size for f in moved)
    return len(df), total_size


def _parse_types(types_arg: str) -> Set[str]:
    valid = {"ohlcv", "ticks", "orders", "fills"}
    requested = set(t.strip().lower() for t in types_arg.split(","))

    type_map = {"fills": "fill_samples"}
    mapped = set()
    for t in requested:
        if t in type_map:
            mapped.add(type_map[t])
        elif t in valid:
            mapped.add(t)
        else:
            log.warning("  Unknown type '%s', skipping", t)
    return mapped


def _check_import(name: str) -> bool:
    return True


def migrate_ohlcv(
    source_dir: Path,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, Any]]:
    target_root = target_dir / WAREHOUSE_SUBDIRS["ohlcv"]
    results = []
    csv_pattern = source_dir / "*_*.csv"
    csv_files = sorted(
        f for f in source_dir.glob("*_*.csv")
        if re.match(r"^[A-Z]+_[A-Z0-9]+\.csv$", f.name)
    )

    if not csv_files:
        log.info("  No OHLCV CSV files found matching pattern <SYMBOL>_<TF>.csv")
        return results

    valid_sources = {"EURUSD", "GBPUSD", "XAUUSD"}
    valid_tfs = {"D1", "H1", "M15"}

    for csv_path in csv_files:
        try:
            symbol, tf = _parse_symbol_tf(csv_path.name)
            if symbol not in valid_sources or tf not in valid_tfs:
                log.info("  Skipping non-target source: %s", csv_path.name)
                continue
        except ValueError as e:
            log.warning("  %s", e)
            continue

        csv_size = csv_path.stat().st_size
        if csv_size == 0:
            log.warning("  Empty source file, skipping: %s", csv_path.name)
            continue

        log.info("  OHLCV: %s (%s, %s, %s bytes)", csv_path.name, symbol, tf, csv_size)

        if dry_run:
            results.append({
                "source": str(csv_path),
                "type": "ohlcv",
                "symbol": symbol,
                "frequency": tf,
                "source_size": csv_size,
                "dry_run": True,
            })
            continue

        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            if len(df) == 0:
                log.warning("  Empty data after reading, skipping: %s", csv_path.name)
                continue
        except Exception as e:
            log.error("  Failed to read %s: %s", csv_path.name, e)
            continue

        df.columns = [c.strip().lower() for c in df.columns]
        expected_cols = {"time", "open", "high", "low", "close", "volume"}
        if not expected_cols.issubset(set(df.columns)):
            log.error("  Missing columns in %s: %s", csv_path.name, expected_cols - set(df.columns))
            continue

        df["time"] = df["time"].apply(_parse_ts)
        df["symbol"] = symbol
        df["frequency"] = tf
        df["source"] = "MT5"
        df["volume"] = df["volume"].astype("int64")

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype("float64")

        df = df[list(WAREHOUSE_SCHEMAS["ohlcv"].keys())]

        partitions = PARTITION_KEYS["ohlcv"]
        row_count, total_size = _write_partitioned(
            df, "ohlcv", target_root, partitions, force, dry_run,
        )

        results.append({
            "source": str(csv_path),
            "type": "ohlcv",
            "symbol": symbol,
            "frequency": tf,
            "source_size": csv_size,
            "row_count": row_count,
            "target_size": total_size,
            "compression_ratio": round(csv_size / total_size, 2) if total_size else 0,
        })

    return results


def migrate_tick_parquets(
    source_dir: Path,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, Any]]:
    target_root = target_dir / WAREHOUSE_SUBDIRS["ticks"]
    results = []
    parquet_files = sorted(source_dir.glob("*_ticks_*.parquet"))

    if not parquet_files:
        log.info("  No tick parquet files found in %s", source_dir)
        return results

    for pq_path in parquet_files:
        pq_size = pq_path.stat().st_size
        if pq_size == 0:
            log.warning("  Empty source file, skipping: %s", pq_path.name)
            continue

        symbol = _parse_symbol_ticks(pq_path.name)
        log.info("  Tick Parquet: %s (%s, %s bytes)", pq_path.name, symbol, pq_size)

        if dry_run:
            results.append({
                "source": str(pq_path),
                "type": "tick_parquet",
                "symbol": symbol,
                "source_size": pq_size,
                "dry_run": True,
            })
            continue

        try:
            table = pq.read_table(str(pq_path))
        except Exception as e:
            log.error("  Failed to read %s: %s", pq_path.name, e)
            continue

        df = table.to_pandas()
        if len(df) == 0:
            log.warning("  Empty table, skipping: %s", pq_path.name)
            continue

        col_map = {}
        for c in df.columns:
            c_lower = c.lower().strip()
            if c_lower == "timestamp_utc":
                col_map[c] = "time"
            elif c_lower == "spread_price":
                col_map[c] = "spread"
            elif c_lower == "volume_real":
                col_map[c] = "volume"
            elif c_lower in ("bid", "ask", "last", "flags", "symbol", "volume"):
                col_map[c] = c_lower
        df = df.rename(columns=col_map)
        df = df[[c for c in col_map.values() if c in df.columns]]

        df["time"] = pd.to_datetime(df["time"])
        df["source"] = "MT5"
        if "symbol" not in df.columns:
            df["symbol"] = symbol

        if "spread" not in df.columns:
            if "ask" in df.columns and "bid" in df.columns:
                df["spread"] = df["ask"] - df["bid"]
            else:
                df["spread"] = 0.0

        df["mid"] = (df["bid"] + df["ask"]) / 2
        df["spread_pips"] = df["spread"] * 10000

        for int_col in ["flags"]:
            if int_col in df.columns:
                df[int_col] = df[int_col].astype("int32")

        for float_col in ["last", "volume", "ask_volume", "spread"]:
            if float_col not in df.columns:
                df[float_col] = 0.0

        present_cols = [c for c in WAREHOUSE_SCHEMAS["ticks"].keys() if c in df.columns]
        extra_cols = [c for c in df.columns if c not in present_cols and c not in ("year", "month")]
        full_cols = present_cols + extra_cols
        df = df[full_cols]

        partitions = PARTITION_KEYS["ticks"]
        row_count, total_size = _write_partitioned(
            df, "ticks", target_root, partitions, force, dry_run,
        )

        results.append({
            "source": str(pq_path),
            "type": "tick_parquet",
            "symbol": symbol,
            "source_size": pq_size,
            "row_count": row_count,
            "target_size": total_size,
            "compression_ratio": round(pq_size / total_size, 2) if total_size else 0,
        })

    return results


def migrate_bulk_ticks(
    source_dir: Path,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, Any]]:
    target_root = target_dir / WAREHOUSE_SUBDIRS["ticks"]
    results = []
    csv_files = sorted(source_dir.glob("*_bulk.csv"))

    if not csv_files:
        log.info("  No bulk tick CSV files found in %s", source_dir)
        return results

    for csv_path in csv_files:
        csv_size = csv_path.stat().st_size
        if csv_size == 0:
            log.warning("  Empty source file, skipping: %s", csv_path.name)
            continue

        symbol = _parse_symbol_bulk(csv_path.name)
        log.info("  Bulk Tick CSV: %s (%s, %s bytes)", csv_path.name, symbol, csv_size)

        if dry_run:
            results.append({
                "source": str(csv_path),
                "type": "bulk_tick_csv",
                "symbol": symbol,
                "source_size": csv_size,
                "dry_run": True,
            })
            continue

        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            if len(df) == 0:
                log.warning("  Empty data, skipping: %s", csv_path.name)
                continue
        except Exception as e:
            log.error("  Failed to read %s: %s", csv_path.name, e)
            continue

        df.columns = [c.strip().lower() for c in df.columns]
        rename_map = {
            "volume_real": "volume",
        }
        df = df.rename(columns=rename_map)

        df["time"] = df["time"].apply(_parse_ts)
        df["source"] = "MT5"
        df["symbol"] = symbol
        df["spread"] = df["ask"] - df["bid"]
        df["mid"] = (df["bid"] + df["ask"]) / 2
        df["spread_pips"] = df["spread"] * 10000

        if "flags" in df.columns:
            df["flags"] = df["flags"].astype("int32")
        if "volume" in df.columns:
            df["volume"] = df["volume"].astype("float64")

        if "ask_volume" not in df.columns:
            df["ask_volume"] = 0.0

        present_cols = [c for c in WAREHOUSE_SCHEMAS["ticks"].keys() if c in df.columns]
        extra_cols = [c for c in df.columns if c not in present_cols and c not in ("year", "month")]
        full_cols = present_cols + extra_cols
        df = df[full_cols]

        partitions = PARTITION_KEYS["ticks"]
        row_count, total_size = _write_partitioned(
            df, "ticks", target_root, partitions, force, dry_run,
        )

        results.append({
            "source": str(csv_path),
            "type": "bulk_tick_csv",
            "symbol": symbol,
            "source_size": csv_size,
            "row_count": row_count,
            "target_size": total_size,
            "compression_ratio": round(csv_size / total_size, 2) if total_size else 0,
        })

    return results


def migrate_fills(
    source_dir: Path,
    target_dir: Path,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, Any]]:
    target_root = target_dir / WAREHOUSE_SUBDIRS["fill_samples"]
    results = []
    csv_files = sorted(source_dir.glob("fill_samples_*.csv"))

    if not csv_files:
        log.info("  No fill sample CSV files found in %s", source_dir)
        return results

    for csv_path in csv_files:
        csv_size = csv_path.stat().st_size
        if csv_size == 0:
            log.warning("  Empty source file, skipping: %s", csv_path.name)
            continue

        log.info("  Fill Samples: %s (%s bytes)", csv_path.name, csv_size)

        if dry_run:
            results.append({
                "source": str(csv_path),
                "type": "fill_samples",
                "source_size": csv_size,
                "dry_run": True,
            })
            continue

        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            if len(df) == 0:
                log.warning("  Empty data, skipping: %s", csv_path.name)
                continue
        except Exception as e:
            log.error("  Failed to read %s: %s", csv_path.name, e)
            continue

        df.columns = [c.strip().lower() for c in df.columns]

        col_map = {
            "decision_time": "time",
            "decision_price": "requested_price",
            "spread_price": "spread_at_fill",
        }
        df = df.rename(columns=col_map)

        df["time"] = df["time"].apply(_parse_ts)

        if "volume" not in df.columns:
            df["volume"] = 1.0

        if "simulation_id" not in df.columns:
            df["simulation_id"] = "legacy_migration"

        if "latency_model" not in df.columns:
            df["latency_model"] = None

        if "tick_sequence_index" not in df.columns:
            df["tick_sequence_index"] = None

        if "sigma_slippage" not in df.columns:
            df["sigma_slippage"] = None

        for col in ["fill_price", "requested_price", "slippage_points", "spread_at_fill"]:
            if col in df.columns:
                df[col] = df[col].astype("float64")

        if "side" in df.columns:
            df["side"] = df["side"].astype(str)

        present_cols = [c for c in WAREHOUSE_SCHEMAS["fill_samples"].keys() if c in df.columns]
        extra_cols = [c for c in df.columns if c not in present_cols and c not in ("year", "month")]
        full_cols = present_cols + extra_cols
        df = df[full_cols]

        partitions = PARTITION_KEYS["fill_samples"]
        row_count, total_size = _write_partitioned(
            df, "fill_samples", target_root, partitions, force, dry_run,
        )

        results.append({
            "source": str(csv_path),
            "type": "fill_samples",
            "source_size": csv_size,
            "row_count": row_count,
            "target_size": total_size,
            "compression_ratio": round(csv_size / total_size, 2) if total_size else 0,
        })

    return results


def _validate_schema(
    target_dir: Path,
    table_type: str,
) -> Dict[str, Any]:
    target_root = target_dir / WAREHOUSE_SUBDIRS[table_type]
    expected = WAREHOUSE_SCHEMAS[table_type]

    if not target_root.exists():
        return {"status": "SKIP", "reason": "No output directory found"}

    parquet_files = list(target_root.rglob("*.parquet"))
    if not parquet_files:
        return {"status": "SKIP", "reason": "No parquet files found"}

    partition_dropped = set(PARTITION_KEYS.get(table_type, []))
    issues = []
    total_rows = 0
    validated_files = 0

    for pf_path in parquet_files[:10]:
        try:
            meta = pq.read_metadata(str(pf_path))
            schema = pq.read_schema(str(pf_path))
            total_rows += meta.num_rows
            validated_files += 1

            schema_names = set(schema.names)
            expected_names = set(expected.keys()) - partition_dropped

            missing = expected_names - schema_names
            if missing:
                issues.append(f"{pf_path.name}: missing columns {missing}")

            for field in schema:
                if field.name in expected:
                    expected_type = expected[field.name]
                    if str(field.type) != str(expected_type):
                        issues.append(
                            f"{pf_path.name}: column '{field.name}' expected "
                            f"{expected_type}, got {field.type}"
                        )
        except Exception as e:
            issues.append(f"{pf_path.name}: read error - {e}")

    if not parquet_files:
        issues.append("No parquet files to validate")

    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "table_type": table_type,
        "files_checked": len(parquet_files),
        "files_validated": validated_files,
        "total_rows": total_rows,
        "issues": issues,
    }


def _print_report(results: List[Dict[str, Any]]) -> None:
    if not results:
        return None

    log.info("")
    log.info("Migration Summary:")
    log.info("%-40s %-12s %-10s %-8s %-12s %s", "Source", "Type", "Symbol", "Rows", "Src Size", "Ratio")
    log.info("-" * 100)

    total_src = 0
    total_tgt = 0
    total_rows = 0

    for r in results:
        symbol = r.get("symbol", "")
        src_size = r.get("source_size", 0)
        tgt_size = r.get("target_size", 0)
        rows = r.get("row_count", 0)
        ratio = r.get("compression_ratio", 0)
        dry = r.get("dry_run", False)

        src_str = f"{src_size:,}" if src_size else "-"
        tgt_str = f"{tgt_size:,}" if tgt_size else "-"
        rows_str = f"{rows:,}" if rows else "DRY"
        ratio_str = f"{ratio}x" if ratio else "-"

        log.info(
            "%-40s %-12s %-10s %-8s %-12s %s",
            Path(r["source"]).name,
            r["type"],
            symbol,
            rows_str if not dry else "dry-run",
            src_str if not dry else "-",
            ratio_str if not dry else "-",
        )

        if not dry:
            total_src += src_size
            total_tgt += tgt_size
            total_rows += rows

    log.info("-" * 100)
    if total_rows:
        overall = total_src / total_tgt if total_tgt else 0
        log.info(
            "Total: %s files, %s rows, %s bytes -> %s bytes (%sx compression)",
            len(results),
            f"{total_rows:,}",
            f"{total_src:,}",
            f"{total_tgt:,}",
            round(overall, 2),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy data formats to standardized warehouse Parquet",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
        help="Legacy source root directory (default: data/)",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=None,
        help="Warehouse root directory (default: <source-dir>/warehouse)",
    )
    parser.add_argument(
        "--types",
        type=str,
        default="ohlcv,ticks,fills",
        help="Comma-separated types to migrate: ohlcv, ticks, fills (default: ohlcv,ticks,fills)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing target files",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output schema against docs/schema.md after migration",
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        log.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    target_dir = Path(args.target_dir).resolve() if args.target_dir else source_dir / "warehouse"

    if not target_dir.exists():
        if args.dry_run:
            log.info("Would create target directory: %s", target_dir)
        else:
            _ensure_dir(target_dir)
            log.info("Created target directory: %s", target_dir)

    types = _parse_types(args.types)
    if not types:
        log.error("No valid types specified. Valid: ohlcv, ticks, fills")
        sys.exit(1)

    log.info("Source:  %s", source_dir)
    log.info("Target:  %s", target_dir)
    log.info("Types:   %s", ", ".join(sorted(types)))
    log.info("Dry-run: %s", args.dry_run)
    log.info("Force:   %s", args.force)
    log.info("")

    all_results: List[Dict[str, Any]] = []

    if "ohlcv" in types:
        log.info("[OHLCV] Migrating OHLCV CSV files...")
        results = migrate_ohlcv(source_dir, target_dir, args.dry_run, args.force)
        all_results.extend(results)
        log.info("")

    if "ticks" in types:
        tick_source_dir = source_dir.parent / "artifacts" / "tick_data"
        log.info("[Ticks] Migrating tick parquet files from %s ...", tick_source_dir)
        results = migrate_tick_parquets(tick_source_dir, target_dir, args.dry_run, args.force)
        all_results.extend(results)

        bulk_source_dir = source_dir.parent / "artifacts" / "mega_data" / "ticks"
        log.info("[Bulk Ticks] Migrating bulk tick CSV files from %s ...", bulk_source_dir)
        results = migrate_bulk_ticks(bulk_source_dir, target_dir, args.dry_run, args.force)
        all_results.extend(results)
        log.info("")

    if "fill_samples" in types:
        fills_source_dir = source_dir.parent / "artifacts" / "fill_samples_fixed"
        log.info("[Fills] Migrating fill sample CSV files from %s ...", fills_source_dir)
        results = migrate_fills(fills_source_dir, target_dir, args.dry_run, args.force)
        all_results.extend(results)
        log.info("")

    _print_report(all_results)

    if args.validate and not args.dry_run:
        log.info("")
        log.info("Validating output schemas...")
        for table_type in types:
            result = _validate_schema(target_dir, table_type)
            status = result["status"]
            if status == "PASS":
                log.info(
                    "  %s: PASS (%s files, %s rows)",
                    table_type,
                    result["files_validated"],
                    result.get("total_rows", 0),
                )
            elif status == "SKIP":
                log.info("  %s: SKIP (%s)", table_type, result.get("reason", ""))
            else:
                log.error("  %s: FAIL", table_type)
                for issue in result["issues"]:
                    log.error("    - %s", issue)


if __name__ == "__main__":
    main()
