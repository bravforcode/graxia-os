"""Thaifxbook collector configuration (public layer, P0)."""

from __future__ import annotations

from pathlib import Path

BASE_URL = "https://thaifxbook.com"
OUTLOOK_URL = f"{BASE_URL}/tools/outlook"
PROFILE_URL = f"{BASE_URL}/p/{{uuid}}"

# Collection cadence: platform syncs MT5 accounts every few hours; snapshot at
# most every 4 hours to stay a full sync-cycle apart (validated 2026-08-06).
SNAPSHOT_INTERVAL_HOURS = 4
REQUEST_DELAY_SECONDS = 2.0
TIMEOUT_SECONDS = 30.0

# Local storage (gitignored; mirrors myfxbook data/ convention).
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DB_PATH = PROJECT_ROOT / "data" / "thaifxbook" / "thaifxbook.duckdb"
RAW_DIR = PROJECT_ROOT / "data" / "thaifxbook" / "raw"
REPORT_DIR = PROJECT_ROOT / "reports" / "thaifxbook"

# Public profiles: full /p/ sitemap is 583+; --limit caps a dry-run/backfill.
DEFAULT_LIMIT = 30

# Progress log for long backfill runs (scheduled tasks have no visible stdout).
LOG_PATH = REPORT_DIR / "collect.log"
