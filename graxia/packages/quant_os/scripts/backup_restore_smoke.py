"""
Backup & Restore Smoke Test

Connects to PostgreSQL, dumps quant_* tables to SQL, verifies row counts
match between source DB and dump. Exits 0 on success, 1 on failure.

Usage:
    python scripts/backup_restore_smoke.py
    python scripts/backup_restore_smoke.py --dsn "postgresql://user:pass@host:5432/db"

Requires: psycopg2-binary (pip install psycopg2-binary)
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


def get_dsn(override: str | None = None) -> str:
    """Resolve DSN from argument, env, or default."""
    if override:
        return override
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("[FAIL] DATABASE_URL not set and no --dsn provided", file=sys.stderr)
        sys.exit(1)
    return dsn


def get_quant_tables(conn) -> list[str]:
    """Return list of tables matching quant_* schema."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'quant_%' "
            "ORDER BY table_name"
        )
        return [row[0] for row in cur.fetchall()]


def get_row_count(conn, table: str) -> int:
    """Get row count for a table (safe — table name is validated)."""
    import re

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
        raise ValueError(f"Unsafe table name: {table}")
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        return cur.fetchone()[0]


def dump_table(conn, table: str, out_dir: Path) -> Path:
    """Dump a single table to a CSV file and return the path."""
    import re

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
        raise ValueError(f"Unsafe table name: {table}")

    out_path = out_dir / f"{table}.csv"
    with conn.cursor() as cur:
        # Use COPY for efficient dump
        with open(out_path, "w", encoding="utf-8") as f:
            cur.copy_expert(f'COPY "{table}" TO STDOUT WITH CSV HEADER', f)
    return out_path


def count_csv_rows(csv_path: Path) -> int:
    """Count data rows in a CSV file (excluding header)."""
    with open(csv_path, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # subtract header


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup & restore smoke test")
    parser.add_argument("--dsn", help="PostgreSQL connection string")
    parser.add_argument("--keep", action="store_true", help="Keep dump files after test")
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("[FAIL] psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        return 1

    dsn = get_dsn(args.dsn)

    # Connect
    print("[INFO] Connecting to database...")
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}", file=sys.stderr)
        return 1

    print("[INFO] Connected successfully")

    # Discover tables
    tables = get_quant_tables(conn)
    if not tables:
        print("[WARN] No quant_* tables found — nothing to back up")
        conn.close()
        return 0

    print(f"[INFO] Found {len(tables)} quant_* tables: {', '.join(tables)}")

    # Dump and verify
    errors: list[str] = []
    dump_dir = Path(tempfile.mkdtemp(prefix="quant_backup_"))
    print(f"[INFO] Dump directory: {dump_dir}")

    for table in tables:
        # Get source row count
        src_count = get_row_count(conn, table)

        # Dump table
        csv_path = dump_table(conn, table, dump_dir)

        # Count rows in dump
        dump_count = count_csv_rows(csv_path)

        if src_count == dump_count:
            print(f"  [OK]   {table}: {src_count} rows (source == dump)")
        else:
            msg = f"  [FAIL] {table}: source={src_count}, dump={dump_count}"
            print(msg)
            errors.append(msg)

    conn.close()

    # Summary
    print()
    if errors:
        print(f"[FAIL] {len(errors)} table(s) had row count mismatches:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(
        f"[PASS] All {len(tables)} tables dumped and verified ({sum(count_csv_rows(p) for p in dump_dir.glob('*.csv'))} total rows)"
    )

    # Cleanup
    if not args.keep:
        import shutil

        shutil.rmtree(dump_dir, ignore_errors=True)
        print("[INFO] Dump files cleaned up")
    else:
        print(f"[INFO] Dump files retained at: {dump_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
