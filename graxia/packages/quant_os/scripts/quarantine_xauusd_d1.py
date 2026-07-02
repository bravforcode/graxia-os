"""Quarantine XAUUSD_D1 data: filter pre-2004 rows and OHLC violations.

Reads data/XAUUSD_D1.csv, applies filters, outputs to data/canonical/XAUUSD_D1_clean.csv,
and generates manifest at data/manifests/XAUUSD_D1_clean.manifest.json.

Quarantined rows are saved to data/quarantine/XAUUSD_D1_quarantined.csv for audit.

Rules:
  - Drop rows before 2004-01-01 (pre-modern gold era, flat synthetic prices)
  - Drop rows where high < max(open, close) or low > min(open, close) (OHLC violation)
  - Drop rows where high < low (impossible)
  - Drop rows where any OHLC <= 0 (invalid prices)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

INPUT_PATH = DATA_DIR / "XAUUSD_D1.csv"
CLEAN_PATH = DATA_DIR / "canonical" / "XAUUSD_D1_clean.csv"
QUARANTINE_PATH = DATA_DIR / "quarantine" / "XAUUSD_D1_quarantined.csv"
MANIFEST_PATH = DATA_DIR / "manifests" / "XAUUSD_D1_clean.manifest.json"

CUTOFF_DATE = "2004-01-01"


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"ERROR: Input file not found: {INPUT_PATH}", file=sys.stderr)
        return 1

    df = pd.read_csv(INPUT_PATH)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    total_raw = len(df)

    # ── Record pre-filter stats ──
    pre_2004 = len(df[df["time"] < CUTOFF_DATE])
    print(f"Raw rows: {total_raw}")
    print(f"Pre-{CUTOFF_DATE} rows: {pre_2004}")

    # ── Filter 1: Drop pre-2004 ──
    mask_pre2004 = df["time"] < CUTOFF_DATE

    # ── Filter 2: OHLC violations ──
    # high < max(open, close) or low > min(open, close)
    mask_h_l = df["high"] < df["low"]
    mask_high_lt_oc = df["high"] < df[["open", "close"]].max(axis=1)
    mask_low_gt_oc = df["low"] > df[["open", "close"]].min(axis=1)

    # ── Filter 3: Non-positive prices ──
    mask_nonpositive = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)

    # Combined quarantine mask
    mask_quarantine = mask_pre2004 | mask_h_l | mask_high_lt_oc | mask_low_gt_oc | mask_nonpositive

    quarantined = df[mask_quarantine].copy()
    clean = df[~mask_quarantine].copy()

    # ── Stats ──
    stats = {
        "pre_2004_rows": int(mask_pre2004.sum()),
        "ohlc_violation_h_lt_l": int(mask_h_l.sum()),
        "ohlc_violation_high_lt_oc": int(mask_high_lt_oc.sum()),
        "ohlc_violation_low_gt_oc": int(mask_low_gt_oc.sum()),
        "nonpositive_prices": int(mask_nonpositive.sum()),
        "total_quarantined": int(mask_quarantine.sum()),
        "total_clean": len(clean),
    }
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # ── Write outputs ──
    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    clean = clean.sort_values("time").reset_index(drop=True)
    clean.to_csv(CLEAN_PATH, index=False)

    quarantined = quarantined.sort_values("time").reset_index(drop=True)
    quarantined.to_csv(QUARANTINE_PATH, index=False)

    # ── Manifest ──
    manifest = {
        "source": str(INPUT_PATH.name),
        "output": str(CLEAN_PATH.relative_to(PROJECT_ROOT)),
        "quarantine_output": str(QUARANTINE_PATH.relative_to(PROJECT_ROOT)),
        "cutoff_date": CUTOFF_DATE,
        "filters": [
            "drop_pre_2004",
            "drop_high_lt_low",
            "drop_high_lt_max_oc",
            "drop_low_gt_min_oc",
            "drop_nonpositive_ohlc",
        ],
        "stats": stats,
        "date_range": {
            "first": clean["time"].min().isoformat() if len(clean) > 0 else None,
            "last": clean["time"].max().isoformat() if len(clean) > 0 else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nClean rows: {len(clean)} -> {CLEAN_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Quarantined rows: {len(quarantined)} -> {QUARANTINE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
