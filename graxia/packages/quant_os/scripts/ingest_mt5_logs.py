#!/usr/bin/env python3
"""MT5 Execution Log Ingestion Pipeline.

Ingests live logs, batch orders, and tick data into a Hive-partitioned
Parquet warehouse with dedup, schema validation, and INV-005 manifests.

Usage:
    python scripts/ingest_mt5_logs.py
        --input artifacts/mega_data
        --output data/warehouse
        --symbols EURUSD,GBPUSD,XAUUSD
        --start-date 2024-01-01
        --end-date 2024-12-31
        --db-path data/warehouse/quantos.duckdb
        --validate
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, UTC
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pyarrow as pa
    import pyarrow.csv as pa_csv
    import pyarrow.parquet as pq
    PYARROW_OK = True
except ImportError:
    pa = pa_csv = pq = None
    PYARROW_OK = False

try:
    import duckdb
    DUCKDB_OK = True
except ImportError:
    duckdb = None
    DUCKDB_OK = False

logger = logging.getLogger("ingest_mt5_logs")

SOURCE_LIVE = "live_logs"
SOURCE_ORDERS = "orders"
SOURCE_TICKS = "ticks"


def _make_logger(verbose: bool = False) -> logging.Logger:
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    if not logger.handlers:
        logger.addHandler(handler)
    return logger





def _sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()


def _hive_path(root: str, source: str, symbol: str, dt: datetime) -> Tuple[str, str]:
    yr = f"{dt.year:04d}"
    mo = f"{dt.month:02d}"
    day_tag = dt.strftime("%Y-%m-%d")
    out_dir = Path(root) / source / f"symbol={symbol}" / f"year={yr}" / f"month={mo}"
    final_path = out_dir / f"{day_tag}.parquet"
    return str(out_dir), str(final_path)


def _parse_timestamp(val: Any, source_type: str) -> Optional[datetime]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=UTC)
        return val
    s = str(val).strip()
    if source_type == SOURCE_TICKS:
        try:
            return datetime.fromtimestamp(float(s), tz=UTC)
        except (ValueError, OSError):
            return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(s.rstrip("Z"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _sanitize_bom(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return f.read()


def _read_csv_to_dicts(filepath: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    content = _sanitize_bom(filepath)
    if not content.strip():
        return [], []
    reader = csv.DictReader(StringIO(content))
    rows = []
    for r in reader:
        rows.append({k: v for k, v in r.items()})
    return rows, reader.fieldnames or []


def _parse_live_logs(
    rows: List[Dict[str, Any]], symbol: str, dt: datetime,
) -> Tuple[List[Dict[str, Any]], int]:
    parsed = []
    errors = 0
    now_utc = datetime.now(UTC)
    for row in rows:
        try:
            ts = row.get("timestamp_utc", "")
            timestamp = _parse_timestamp(ts, SOURCE_LIVE)
            if timestamp is None:
                errors += 1
                continue
            parsed.append({
                "timestamp_utc": timestamp,
                "balance": _safe_float(row.get("balance")),
                "equity": _safe_float(row.get("equity")),
                "margin": _safe_float(row.get("margin")),
                "margin_level": _safe_float(row.get("margin_level")),
                "profit": _safe_float(row.get("profit")),
                "spread_points": _safe_float(row.get("spread_points")),
                "bid": _safe_float(row.get("bid")),
                "ask": _safe_float(row.get("ask")),
                "open_positions": _safe_int(row.get("open_positions")),
                "source": row.get("source", "mt5").strip(),
                "symbol": symbol,
                "ingestion_timestamp": now_utc,
            })
        except Exception:
            errors += 1
    return parsed, errors


def _parse_orders(
    rows: List[Dict[str, Any]], symbol: str, dt: datetime,
) -> Tuple[List[Dict[str, Any]], int]:
    parsed = []
    errors = 0
    now_utc = datetime.now(UTC)
    for row in rows:
        try:
            row_sym = str(row.get("symbol", "")).upper()
            send_ts = _parse_timestamp(row.get("send_time", ""), SOURCE_ORDERS)
            close_ts = _parse_timestamp(row.get("close_time", ""), SOURCE_ORDERS)
            parsed.append({
                "order_id": str(row.get("order_id", "")),
                "symbol": row_sym,
                "side": str(row.get("side", "")),
                "volume": _safe_float(row.get("volume")),
                "entry": _safe_float(row.get("entry")),
                "sl": _safe_float(row.get("sl")),
                "tp": _safe_float(row.get("tp")),
                "send_retcode": _safe_int(row.get("send_retcode")),
                "send_deal": _safe_int(row.get("send_deal")),
                "send_price": _safe_float(row.get("send_price")),
                "send_time": send_ts,
                "close_retcode": _safe_int(row.get("close_retcode")),
                "close_deal": _safe_int(row.get("close_deal")),
                "close_time": close_ts,
                "slippage_points": _safe_float(row.get("slippage_points")),
                "latency_ms": _safe_int(row.get("latency_ms")),
                "status": str(row.get("status", "")),
                "source": SOURCE_ORDERS,
                "ingestion_timestamp": now_utc,
            })
        except Exception:
            errors += 1
    return parsed, errors


def _parse_ticks(
    rows: List[Dict[str, Any]], symbol: str, dt: datetime,
) -> Tuple[List[Dict[str, Any]], int]:
    parsed = []
    errors = 0
    now_utc = datetime.now(UTC)
    for row in rows:
        try:
            ts = _parse_timestamp(row.get("time", ""), SOURCE_TICKS)
            if ts is None:
                errors += 1
                continue
            parsed.append({
                "timestamp_utc": ts,
                "bid": _safe_float(row.get("bid")),
                "ask": _safe_float(row.get("ask")),
                "last": _safe_float(row.get("last")),
                "volume": _safe_float(row.get("volume_real")),
                "symbol": symbol,
                "source": SOURCE_TICKS,
                "ingestion_timestamp": now_utc,
            })
        except Exception:
            errors += 1
    return parsed, errors


def _validate_schema(
    columns: List[str], expected: List[str], label: str,
) -> List[str]:
    missing = [c for c in expected if c not in columns]
    if missing:
        logger.warning("%s: missing columns: %s", label, missing)
    return missing


def _dedup_rows(rows: List[Dict[str, Any]], keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    seen = {}
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        seen[key] = row
    return list(seen.values())


def _quality_report(rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"rows": 0}
    null_counts = {}
    nan_counts = {}
    for col in rows[0]:
        nulls = sum(1 for r in rows if r.get(col) is None or r.get(col) == "")
        null_counts[col] = nulls
        nan_counts[col] = sum(
            1 for r in rows
            if isinstance(r.get(col), float) and (r[col] != r[col])
        )
    issues = {}
    for col in null_counts:
        if null_counts[col] > 0:
            issues[f"null_{col}"] = null_counts[col]
    for col in nan_counts:
        if nan_counts[col] > 0:
            issues[f"nan_{col}"] = nan_counts[col]
    report = {
        "rows": n,
        "null_counts": {k: v for k, v in null_counts.items() if v > 0},
        "nan_counts": {k: v for k, v in nan_counts.items() if v > 0},
    }
    if issues:
        logger.warning("%s quality issues: %s", label, issues)
    return report


def _rows_to_table(rows: List[Dict[str, Any]], schema: pa.Schema) -> pa.Table:
    if not rows:
        return pa.Table.from_pylist([], schema=schema)
    return pa.Table.from_pylist(rows, schema=schema)


def _write_parquet_atomic(table: pa.Table, final_path: str):
    out_dir = os.path.dirname(final_path)
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".parquet",
        dir=out_dir,
    )
    os.close(fd)
    try:
        pq.write_table(table, tmp_path, version="2.6", use_dictionary=False)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(tmp_path, final_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    logger.info("Wrote %s (%d rows)", final_path, table.num_rows)


def _register_duckdb(
    db_path: str, table_name: str, parquet_path: str,
) -> bool:
    if not DUCKDB_OK:
        logger.debug("DuckDB not available, skipping registration")
        return False
    try:
        conn = duckdb.connect(db_path)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} AS
            SELECT * FROM read_parquet('{parquet_path}')
        """)
        conn.close()
        logger.info("Registered %s in %s", table_name, db_path)
        return True
    except Exception as e:
        logger.warning("DuckDB registration failed: %s", e)
        return False


def _write_manifest(
    parquet_path: str, source: str, symbol: str, date_str: str, rows: int, columns: List[str],
    manifest_root: str, quality: Dict[str, Any],
):
    manifest_dir = Path(manifest_root)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"INV-005-{source}-{symbol}-{date_str}.json"

    tmp = manifest_path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        json.dump({
            "spec": "INV-005",
            "schema_version": "1.0",
            "source": source,
            "symbol": symbol,
            "date": date_str,
            "rows": rows,
            "columns": columns,
            "sha256": _sha256(parquet_path),
            "quality": quality,
            "ingested_at_utc": datetime.now(UTC).isoformat(),
        }, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    try:
        if manifest_path.exists():
            manifest_path.unlink()
        shutil.move(str(tmp), str(manifest_path))
        logger.info("Manifest: %s", manifest_path)
    except PermissionError:
        logger.warning("Manifest write deferred (concurrent access): %s", manifest_path)
        if tmp.exists():
            tmp.unlink()


def _find_live_logs(input_dir: str, symbols: List[str], start_str: str, end_str: str) -> List[Tuple[str, str, datetime]]:
    found = []
    base = Path(input_dir) / "live_logs"
    if not base.exists():
        logger.debug("No live_logs directory at %s", base)
        return found
    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    for sym in symbols:
        sym_dir = base / sym
        if not sym_dir.is_dir():
            continue
        for fpath in sorted(sym_dir.glob("logs_*.csv")):
            date_part = fpath.stem.replace("logs_", "")
            try:
                file_dt = datetime.strptime(date_part, "%Y%m%d")
            except ValueError:
                continue
            if start_dt <= file_dt <= end_dt:
                found.append((str(fpath), sym, file_dt))
    return found


def _find_orders(input_dir: str, symbols: List[str], start_str: str, end_str: str) -> List[Tuple[str, str, datetime]]:
    found = []
    base = Path(input_dir) / "orders"
    if not base.exists():
        logger.debug("No orders directory at %s", base)
        return found
    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    patterns = ["batch_*.csv", "batch_*.parquet"]
    for pat in patterns:
        for fpath in sorted(base.glob(pat)):
            fname = fpath.stem
            if fname.startswith("batch_"):
                date_part = fname.split("_")[1][:8] if "_" in fname else ""
            else:
                continue
            try:
                file_dt = datetime.strptime(date_part, "%Y%m%d")
            except (ValueError, IndexError):
                continue
            if start_dt <= file_dt <= end_dt:
                found.append((str(fpath), "ALL", file_dt))
    return found


def _find_ticks(input_dir: str, symbols: List[str], start_str: str, end_str: str) -> List[Tuple[str, str, datetime]]:
    found = []
    base = Path(input_dir) / "ticks"
    if not base.exists():
        logger.debug("No ticks directory at %s", base)
        return found
    for sym in symbols:
        for fpath in base.glob(f"{sym}_bulk.csv"):
            found.append((str(fpath), sym, None))
        for fpath in base.glob(f"{sym}_bulk.parquet"):
            found.append((str(fpath), sym, None))
    return found


def _read_parquet_rows(filepath: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        pf = pq.ParquetFile(filepath)
        table = pf.read()
        cols = table.column_names
        rows = table.to_pylist()
        return rows, cols
    except Exception as e:
        logger.warning("Failed to read %s: %s", filepath, e)
        return [], []


def _ingest_source(
    files: List[Tuple[str, str, datetime]],
    parse_fn,
    schema: pa.Schema,
    source_label: str,
    output_root: str,
    manifest_root: str,
    db_path: Optional[str],
    mode: str,
    validate: bool,
) -> Dict[str, Any]:
    total_rows = 0
    total_errors = 0
    total_files = 0
    per_source_stats: Dict[str, Any] = {}

    for filepath, symbol, file_dt in files:
        total_files += 1
        fname = os.path.basename(filepath)
        label = f"{source_label}/{fname}"

        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".parquet":
                raw_rows, columns = _read_parquet_rows(filepath)
                if not raw_rows:
                    logger.info("%s: empty or unreadable, skipping", label)
                    continue
            else:
                raw_rows, columns = _read_csv_to_dicts(filepath)
                if not raw_rows:
                    logger.info("%s: empty file, skipping", label)
                    continue

            _validate_schema(columns, list(schema.names), label)
            expected_cols = list(schema.names)

            parsed, errs = parse_fn(raw_rows, symbol, file_dt)
            total_errors += errs

            if not parsed:
                logger.info("%s: no rows parsed, skipping", label)
                continue

            groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for row in parsed:
                sym = row.get("symbol", "UNKNOWN") or "UNKNOWN"
                ts = row.get("timestamp_utc") or row.get("send_time")
                if isinstance(ts, datetime):
                    date_key = ts.strftime("%Y-%m-%d")
                elif file_dt is not None:
                    date_key = file_dt.strftime("%Y-%m-%d")
                else:
                    date_key = "unknown"
                groups.setdefault((sym, date_key), []).append(row)

            dedup_keys = ("timestamp_utc", "send_time", "symbol", "source")

            for (sym, date_key), sym_rows in groups.items():
                dt_obj = datetime.strptime(date_key, "%Y-%m-%d")
                _, final_path = _hive_path(output_root, source_label, sym, dt_obj)

                if mode == "append" and os.path.exists(final_path):
                    existing_rows, _ = _read_parquet_rows(final_path)
                    combined = existing_rows + sym_rows
                    combined = _dedup_rows(combined, dedup_keys)
                    table = _rows_to_table(combined, schema)
                else:
                    combined = _dedup_rows(sym_rows, dedup_keys)
                    table = _rows_to_table(combined, schema)

                _write_parquet_atomic(table, final_path)

                if validate:
                    qual = _quality_report(combined, label)
                else:
                    qual = {"rows": len(combined)}

                _write_manifest(
                    final_path, source_label, sym, date_key,
                    len(combined), expected_cols, manifest_root, qual,
                )

                if db_path:
                    tbl_name = f"{source_label}_{sym}".replace("-", "_").lower()
                    _register_duckdb(db_path, tbl_name, final_path)

                total_rows += len(sym_rows)
                per_source_stats[f"{sym}/{date_key}"] = len(sym_rows)

        except Exception as e:
            logger.error("%s: ingestion failed: %s", label, e, exc_info=True if logger.isEnabledFor(logging.DEBUG) else False)
            total_errors += 1

    return {"files": total_files, "rows": total_rows, "errors": total_errors, "details": per_source_stats}


def _validate_pipeline(
    manifest_root: str, source: str, symbol: str, date_str: str,
) -> Dict[str, Any]:
    manifest_name = f"INV-005-{source}-{symbol}-{date_str}.json"
    manifest_path = Path(manifest_root) / manifest_name
    if not manifest_path.exists():
        return {"valid": False, "error": f"manifest not found: {manifest_name}"}
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        parquet_path = None
        base = Path(manifest_root).parent
        expected_path = base / source / f"symbol={symbol}" / f"year={date_str[:4]}" / f"month={date_str[5:7]}" / f"{date_str}.parquet"
        if expected_path.exists():
            parquet_path = str(expected_path)
        actual_sha = _sha256(parquet_path) if parquet_path else None
        return {
            "valid": manifest["sha256"] == actual_sha if actual_sha else False,
            "manifest_sha": manifest["sha256"],
            "actual_sha": actual_sha,
            "rows_in_manifest": manifest.get("rows"),
            "parquet_exists": parquet_path is not None,
            "manifest": manifest_path,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def parse_args(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        description="MT5 Execution Log Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", type=str, default="artifacts/mega_data",
        help="Source data directory (default: artifacts/mega_data)",
    )
    parser.add_argument(
        "--output", type=str, default="data/warehouse",
        help="Warehouse output root (default: data/warehouse)",
    )
    parser.add_argument(
        "--symbols", type=str, default="EURUSD,GBPUSD,XAUUSD",
        help="Comma-separated symbols (default: EURUSD,GBPUSD,XAUUSD)",
    )
    parser.add_argument(
        "--start-date", type=str, default="2024-01-01",
        help="Start date YYYY-MM-DD (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end-date", type=str, default="2024-12-31",
        help="End date YYYY-MM-DD (default: 2024-12-31)",
    )
    parser.add_argument(
        "--db-path", type=str, default=None,
        help="Optional DuckDB database path for table registration",
    )
    parser.add_argument(
        "--mode", type=str, default="append", choices=["append", "overwrite"],
        help="Ingestion mode: append (skip ingested) or overwrite (replace) (default: append)",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run quality checks and validate existing warehouse data",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Verbose logging",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    _make_logger(args.verbose)

    if not PYARROW_OK:
        logger.error("pyarrow is required. Install with: pip install pyarrow")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    input_dir = os.path.abspath(args.input) if not os.path.isabs(args.input) else args.input
    output_root = os.path.abspath(args.output) if not os.path.isabs(args.output) else args.output
    manifest_root = os.path.join(output_root, "manifests")

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        logger.error("No symbols specified")
        sys.exit(1)

    start_str = args.start_date
    end_str = args.end_date
    try:
        _parse_date(start_str)
        _parse_date(end_str)
    except ValueError as e:
        logger.error("Invalid date format: %s", e)
        sys.exit(1)

    os.makedirs(output_root, exist_ok=True)
    os.makedirs(manifest_root, exist_ok=True)

    db_path = args.db_path
    if db_path:
        db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        if DUCKDB_OK:
            logger.info("DuckDB registration enabled: %s", db_path)
        else:
            logger.warning("DuckDB not installed; --db-path will be ignored")

    results = {}

    logger.info("=" * 50)
    logger.info("MT5 Execution Log Ingestion")
    logger.info("  Input:  %s", input_dir)
    logger.info("  Output: %s", output_root)
    logger.info("  Symbols: %s", symbols)
    logger.info("  Range:  %s -> %s", start_str, end_str)
    logger.info("  Mode:   %s", args.mode)
    logger.info("=" * 50)

    logger.info("[1/3] Ingesting live logs ...")
    live_files = _find_live_logs(input_dir, symbols, start_str, end_str)
    if live_files:
        r = _ingest_source(
            live_files, _parse_live_logs, _live_log_schema(),
            SOURCE_LIVE, output_root, manifest_root, db_path, args.mode, args.validate,
        )
        results["live_logs"] = r
        logger.info("  live_logs: %d files, %d rows, %d errors", r["files"], r["rows"], r["errors"])
    else:
        logger.info("  No live logs found")

    logger.info("[2/3] Ingesting order batches ...")
    order_files = _find_orders(input_dir, symbols, start_str, end_str)
    if order_files:
        r = _ingest_source(
            order_files, _parse_orders, _order_schema(),
            SOURCE_ORDERS, output_root, manifest_root, db_path, args.mode, args.validate,
        )
        results["orders"] = r
        logger.info("  orders: %d files, %d rows, %d errors", r["files"], r["rows"], r["errors"])
    else:
        logger.info("  No order files found")

    logger.info("[3/3] Ingesting tick data ...")
    tick_files = _find_ticks(input_dir, symbols, start_str, end_str)
    if tick_files:
        r = _ingest_source(
            tick_files, _parse_ticks, _tick_schema(),
            SOURCE_TICKS, output_root, manifest_root, db_path, args.mode, args.validate,
        )
        results["ticks"] = r
        logger.info("  ticks: %d files, %d rows, %d errors", r["files"], r["rows"], r["errors"])
    else:
        logger.info("  No tick files found")

    logger.info("=" * 50)
    total_rows = sum(v["rows"] for v in results.values())
    total_files = sum(v["files"] for v in results.values())
    total_errors = sum(v["errors"] for v in results.values())
    logger.info("Ingestion complete: %d files, %d rows, %d errors", total_files, total_rows, total_errors)

    if args.validate:
        logger.info("Running post-ingestion validation ...")
        validation_results = {}
        for source in results:
            for key in results[source].get("details", {}):
                parts = key.split("/")
                if len(parts) == 2:
                    sym, date_str = parts
                    v = _validate_pipeline(manifest_root, source, sym, date_str)
                    validation_results[f"{source}/{key}"] = v
                    status = "PASS" if v.get("valid") else "FAIL"
                    logger.info("  %s/%s: %s", source, key, status)
        results["validation"] = validation_results

    summary_path = os.path.join(output_root, "ingestion_summary.json")
    tmp = summary_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(results, f, indent=2, default=str)
    os.replace(tmp, summary_path)
    logger.info("Summary: %s", summary_path)


def _live_log_schema() -> pa.Schema:
    return pa.schema([
        pa.field("timestamp_utc", pa.timestamp("us", tz="UTC")),
        pa.field("balance", pa.float64()),
        pa.field("equity", pa.float64()),
        pa.field("margin", pa.float64()),
        pa.field("margin_level", pa.float64()),
        pa.field("profit", pa.float64()),
        pa.field("spread_points", pa.float64()),
        pa.field("bid", pa.float64()),
        pa.field("ask", pa.float64()),
        pa.field("open_positions", pa.int64()),
        pa.field("source", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC")),
    ])


def _order_schema() -> pa.Schema:
    return pa.schema([
        pa.field("order_id", pa.string()),
        pa.field("symbol", pa.string()),
        pa.field("side", pa.string()),
        pa.field("volume", pa.float64()),
        pa.field("entry", pa.float64()),
        pa.field("sl", pa.float64()),
        pa.field("tp", pa.float64()),
        pa.field("send_retcode", pa.int64()),
        pa.field("send_deal", pa.int64()),
        pa.field("send_price", pa.float64()),
        pa.field("send_time", pa.timestamp("us", tz="UTC")),
        pa.field("close_retcode", pa.int64()),
        pa.field("close_deal", pa.int64()),
        pa.field("close_time", pa.timestamp("us", tz="UTC")),
        pa.field("slippage_points", pa.float64()),
        pa.field("latency_ms", pa.int64()),
        pa.field("status", pa.string()),
        pa.field("source", pa.string()),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC")),
    ])


def _tick_schema() -> pa.Schema:
    return pa.schema([
        pa.field("timestamp_utc", pa.timestamp("us", tz="UTC")),
        pa.field("bid", pa.float64()),
        pa.field("ask", pa.float64()),
        pa.field("last", pa.float64()),
        pa.field("volume", pa.float64()),
        pa.field("symbol", pa.string()),
        pa.field("source", pa.string()),
        pa.field("ingestion_timestamp", pa.timestamp("us", tz="UTC")),
    ])


if __name__ == "__main__":
    main()
