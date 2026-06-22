# G0 Test Migration Ledger Baseline

## Source of Truth
- Primary ledger: `TEST_MIGRATION_RECORD.md`
- Supporting audit: `reports/PHASE_3_1A_1_LEGACY_TEST_MIGRATION_AUDIT.md`

## Baseline Status on 2026-06-23
- A test migration ledger already exists and records deleted, restored, and migrated tests across BE-P7 through BE-P10.
- No Phase 0 task in this run moved, deleted, skipped, quarantined, or replaced existing tests.
- Phase 0 added only targeted scanner verification coverage:
  - `tests/test_secret_scan_script.py`

## Ledger Interpretation
- Existing migration history remains authoritative for prior phases.
- This baseline confirms there was no silent test removal in this Phase 0 branch lane.

## Phase 0 Additions
| File | Type | Reason |
|---|---|---|
| `tests/test_secret_scan_script.py` | Added | Lock `scripts/secret_scan.py` to the correct repo scope and artifact coverage |
