#!/usr/bin/env python3
"""Thaifxbook public-data collector CLI.

Cadence: run every SNAPSHOT_INTERVAL_HOURS (4h) — the platform syncs MT5
accounts every few hours, so this stays a full sync-cycle apart.

Usage:
    python scripts/collect_thaifxbook.py --dry-run --limit 2
    python scripts/collect_thaifxbook.py --db data/thaifxbook/thaifxbook.duckdb
    python scripts/collect_thaifxbook.py --uuids <uuid> <uuid>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # package root

from market_data.thaifxbook import (
    config,  # noqa: E402
    runner_impl,  # noqa: E402
)


def _known_uuids() -> list[str]:
    """Seed profiles: 2 validated accounts + a few from the 2026-08-06 feed.

    A full backfill should read the /p/ sitemap (912 URLs) instead; --limit
    caps this pilot list.
    """
    return [
        "ff65308c-aeda-4cc9-ac85-ce469e98dbaa",  # PutDejudom (validated Phase 0)
        "5899683f-7175-4628-bf40-f8e4ea333f50",  # Electricty Bill (8,343 trades)
        "982d9b44-45ab-4b57-a852-a01a64fded4d",  # Gremax (masked account)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Thaifxbook public data")
    parser.add_argument("--dry-run", action="store_true", help="fetch + parse but do not write DB")
    parser.add_argument(
        "--limit", type=int, default=config.DEFAULT_LIMIT, help="only first N pilot accounts (default: %(default)s)"
    )
    parser.add_argument("--db", default=str(config.DB_PATH), help="duckdb path (default: %(default)s)")
    parser.add_argument("--uuids", nargs="*", default=None, help="explicit account UUIDs (overrides pilot list)")
    parser.add_argument("--no-outlook", action="store_true", help="skip the /tools/outlook sentiment snapshot")
    args = parser.parse_args()

    uuids = args.uuids if args.uuids else _known_uuids()[: args.limit]
    result = runner_impl.run(
        db_path=args.db,
        account_uuids=uuids,
        dry_run=args.dry_run,
        with_outlook=not args.no_outlook,
    )

    print(
        f"[{result.ts:%Y-%m-%d %H:%M:%S}] outlook_rows={result.outlook_rows} "
        f"profiles={result.profiles} trades={result.trades} "
        f"errors={len(result.errors)} dry_run={args.dry_run}"
    )
    for err in result.errors:
        print(f"  ERROR {err}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
