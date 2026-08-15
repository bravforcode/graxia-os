# Trial #2001 Date Range — Verification Verdict (2026-08-06)

**Task:** Sub-project A #1 — verify the Knowledge Dump claim "2005-2018, 12.99 ปี" for trial 2001 vs actual data used.

## Evidence chain (all verified 2026-08-06)

1. **Registry** (`research/hypothesis_registry.json` L262-266, trial 2001): `data_range: {start: 2005-01-03, end: 2018-01-01, years: 12.99}`.
2. **Report artifact** (`reports/edge_search_cross_sectional_20260720.json`): same data_range 2005-2018; `per_asset.*.days: 11061` for ALL 7 assets.
3. **ORIGINAL_BACKUP** identical to current report — artifact was NOT tampered.
4. **Loader** (`scripts/edge_search_cross_sectional.py` L208-221 `load_asset_data`): filters `>= 2005-01-01` ONLY — NO upper bound. L641-643 computes data_start/data_end/years from actual data index (not hardcoded).
5. **`_extract_daily_returns`** (L111-114): `days = len(equity_curve)` = number of bars engine processed (one equity point per bar, engine.py L633/L1531).
6. **CSV today** (`data/EURUSD_D1.csv`): 5,936 rows, 2005-01-01 → 2026-07-29, 0 duplicates.
7. **Git history of EURUSD_D1.csv:**
   - `3bf6b2e7` (2026-07-01): "Stooq bulk data ingestion - D1 data for 13 symbols (55k+ rows each)" — EURUSD_D1.csv +19,220 lines (~24k rows, included synthetic pre-inception backfill).
   - `d03a354e` (2026-07-29): "rebuild data files — remove synthetic pre-inception backfill" — 6 files, 116,751 deletions; EURUSD_D1.csv -20,156 lines → 5,936 rows.
   - **Trial 2001 ran 2026-07-20 — BETWEEN these two commits** → it consumed the Stooq CSV (~24k rows incl. synthetic backfill).

## Verdict

| Question | Answer |
|---|---|
| Knowledge Dump "2005-2018 12.99y" accurate? | Metadata was accurate at run time (recorded from actual data), but the data used was the Stooq ~24k-row CSV (mixed synthetic pre-2005 backfill), NOT a clean 12.99-year D1 series |
| CSV reaches 2026? | Yes TODAY (post d03a354e rebuild, 2005→2026-07-29), but NOT at trial run time (07-20) |
| days=11061 explained? | Yes — len(equity_curve) from Stooq multi-TF CSV (~24k rows, subset >=2005) |
| Verdict computed on clean data? | **NO — computed on Stooq data with synthetic pre-2005 backfill** (later removed by d03a354e) |

## Consequence

- Trial 2001 (momentum factor rotation, cross-sectional) REJECT verdict was computed on data later proven contaminated (synthetic pre-inception backfill).
- This CONFIRMS checklist #9 (provenance backfill contamination) for trial 2001 specifically.
- REJECT direction is low-risk (a strategy that could have been inflated by synthetic data still REJECTED), consistent with the #45 logic — but the verdict's data-basis is now known-contaminated. Re-run on clean 2005→2026 data (5,936 rows) is the recommended resolution before treating this verdict as final.
- **Recommended action:** flag trial 2001 as NEEDS_RERUN_ON_CLEAN_DATA in checklist #9/#1; the data_range metadata (12.99y) should be annotated as "Stooq-era, pre-rebuild" in the registry.

---
END OF CONTENT
