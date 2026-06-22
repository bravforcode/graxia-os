# Test Migration Record — BE-P8.1 Audit

## Deleted Tests (11 files)

### Phase 4 tests (deleted in BE-P7 commit `3ae373f`)
| File | Deleted In | Reason | Status |
|------|-----------|--------|--------|
| `tests/test_phase_4_contamination.py` | BE-P7 (`3ae373f`) | API changed: `AntiContaminationGuard` moved to `markets.eurusd.anti_contamination` | **RESTORED** — module still exists, tests valid |
| `tests/test_phase_4_eurusd.py` | BE-P7 (`3ae373f`) | API changed: `EURUSDContractSnapshot` moved to `markets.eurusd.contract_snapshot` | **RESTORED** — module still exists, tests valid |
| `tests/test_phase_4_integration.py` | BE-P7 (`3ae373f`) | API changed: same as above | **RESTORED** — module still exists, tests valid |

### Phase 6 tests (deleted in BE-P8 commit `56113fd`)
| File | Deleted In | Reason | Status |
|------|-----------|--------|--------|
| `tests/test_phase_6_integration.py` | BE-P8 (`56113fd`) | API changed: `ShadowPipeline` moved from `shadow.pipeline` to `shadow.shadow_pipeline` | **MIGRATED** — tests adapted to new API |

### Phase 7 tests (deleted in BE-P9 commit `3ca14eb`)
| File | Deleted In | Reason | Status |
|------|-----------|--------|--------|
| `tests/test_phase_7_canary.py` | BE-P9 (`3ca14eb`) | API changed: `CanaryOrder` renamed to `OrderLifecycle`, `PostFillVerifier` removed | **MIGRATED** — tests adapted to `OrderLifecycle` |
| `tests/test_phase_7_canary_policy.py` | BE-P9 (`3ca14eb`) | API changed: `DemoCanaryPolicy` moved to `canary.demo_policy` | **RESTORED** — module still exists, tests valid |
| `tests/test_phase_7_integration.py` | BE-P9 (`3ca14eb`) | API changed: same as above | **MIGRATED** — tests adapted to current API |

### Phase 8 tests (deleted in BE-P10 commit `ae946c6`)
| File | Deleted In | Reason | Status |
|------|-----------|--------|--------|
| `tests/test_phase_8_integration.py` | BE-P10 (`ae946c6`) | API changed: `DrillExecutor` and `DRILL_CATALOG` import paths changed | **RESTORED** — module still exists, tests valid |
| `tests/test_phase_8_scorecard.py` | BE-P10 (`ae946c6`) | API changed: `DemoScorecard` API changed | **RESTORED** — module still exists, tests valid |

## Migration Principle
- Deleted because API changed ≠ tests are wrong
- Every deleted test must be restored or migrated, not silently dropped
- If module still exists → restore tests with updated imports
- If module renamed → migrate tests to new API
- If module removed → quarantine with owner/reason/expiry

## Verification
All restored/migrated tests pass as of BE-P8.1 commit.
