# Universe Truth-up Evidence (2026-08-06)

**Task:** C1.2 of Tier 0 sweep (spec §5.2, §8.3). Decision rule: borrowed multi-day sampling bar (>=1500 samples/symbol over multi-day window) — a borrowed design DEFINITION, NOT a proven precedent (Direction G Step 1 sampler never ran, spec §2.5).

## Symbol Status Table

| Symbol | Status (after C1.1) | Evidence (cost_calibration.json) | Meets multi-day bar? |
|---|---|---|---|
| EURUSD | measuring (provisional) | L209-263: FROM_TICKS, 56,115 ticks, 4.42 days (2026-07-31→08-05 UTC), mt5_copy_ticks_range_backfill, RT 14.17 bps | YES |
| BTCUSD | measuring (provisional) | L152-170: FROM_TICKS, 1,295,870 ticks, 4.4 days (2026-07-31→08-05 UTC), mt5_copy_ticks_range_backfill, RT 24.75 bps | YES |
| GBPUSD | excluded (with evidence note) | L265-283: FROM_TICKS, 214,512 ticks, BUT 24h tick parquet (2026-06-25), 1 day, tick_parquet, RT 7.15 bps | NO |
| US30 | excluded (with evidence note) | single-day tick parquet (2026-06-25), 1 day, tick_parquet | NO |

## What Changed (C1.1 commit cd0f4983)

1. EURUSD: removed from `excluded` (stale "No cost data" reason) — kept in `measuring`
2. BTCUSD: removed from `excluded` (stale reason) — kept in `measuring` (scope extension, same rule + same evidence class as EURUSD)
3. GBPUSD: removed from `measuring` — kept in `excluded` with corrected reason: "Single-day 2026-06-25 tick parquet only (measurement_duration_days=1, mode=tick_parquet) — does not meet multi-day sampling bar; re-measure required under any future Direction H sampling"
4. US30: removed from `measuring` — kept in `excluded` with corrected single-day reason (old reason falsely claimed "no cost calibration data" despite real tick data; scope extension, same rule)

## Verification (run 2026-08-06)

- `json.load` → valid
- No symbol in 2+ arrays (dupe check) → {} (clean)
- EURUSD measuring=True excluded=False; GBPUSD measuring=False excluded=True; BTCUSD measuring=True excluded=False
- `test_provenance.py` → 6/6 passed (require_cost_calibrated gate intact)

## Notes

- Threshold is a borrowed design definition per spec §5.2; Direction G Step 1 sampler never actually ran (§2.5) — this is NOT validated-proven-precendent evidence.
- GBPUSD re-measure would require a future Direction H sampling plan (Sub-project B decision list item).

---
END OF CONTENT
