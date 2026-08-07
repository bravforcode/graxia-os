# Deprecation evidence — governance/validation_stack.py (#18)

**Date:** 2026-08-07
**Item:** #18 — `validation_stack` false-pass design decision
**Action:** `governance/validation_stack.py` DEPRECATED (docstring added); superseded by `validation/pipeline/gates.py` (GateStatus.ERRORED, SP1 2026-08-04). Resolves DEEP_AUDIT_FINDINGS.md L193-194 P1 false-pass bugs by deprecation (no fix in the legacy module).

## Scan
`rg -l "validation_stack"` across monorepo root, excluding `.git/`, `**/node_modules/**`, `backend/venv/`.

**Total files matched: 15**

| # | File | Classification | Note |
|---|------|---------------|------|
| 1 | `QUANT_OS_MASTER_OPEN_ITEMS.md` | doc-only | Master tracker row #18 — status updated to CLOSED 2026-08-07 |
| 2 | `graxia/packages/quant_os/docs/superpowers/specs/2026-08-06-direction-i-ea-funnel-design.md` | doc-only | Cites historical `reports/validation_stack_false_pass_20260729.md` (trial #2012 n_trials=4 false pass) |
| 3 | `graxia/packages/quant_os/docs/superpowers/plans/2026-08-04-myfxbook-collector-pipeline.md` | doc-only | Describes old `ValidationStack.run_all -> all_passed()` API; documents the deprecated pure-boolean model |
| 4 | `graxia/packages/quant_os/DEEP_AUDIT_FINDINGS.md` | doc-only | L193-194 P1 false-pass findings (PBOCheck IS=0/OOS<0; DeflatedSharpeRatio n_trials==1) — the bugs resolved by deprecation |
| 5 | `graxia/packages/quant_os/validation/pipeline/runner.py` | doc-only | L302 comment: "SP1 (2026-08-04): replaced the governance/validation_stack pseudo-DSR" — superseding module, reference only, no import |
| 6 | `graxia/packages/quant_os/market_data/myfxbook/README.md` | doc-only | "nothing here bypasses governance/validation_stack.py gates" |
| 7 | `graxia/packages/quant_os/MEGA_PLAN_v2_Quant_OS_Live_Readiness.md` | doc-only | F18 scope-clarification item references the module |
| 8 | `graxia/packages/quant_os/quant_os.egg-info/SOURCES.txt` | packaged | Generated setuptools manifest lists `governance/validation_stack.py` (module remains packaged for legacy test compat) |
| 9 | `graxia/packages/quant_os/reports/COMPLIANCE_MATRIX.md` | doc-only | Directory-tree rendering |
| 10 | `graxia/packages/quant_os/reports/deep_research_live_readiness_20260731.md` | doc-only | Task 0-Pre.6 F17/F18 evidence-base integrity mention |
| 11 | `graxia/packages/quant_os/reports/deep_research_institutional_gates_20260803.md` | doc-only | References `run_ws_a_trial_1028.py` using governance/validation_stack as template |
| 12 | `graxia/packages/quant_os/research/pre_registration/trial_1028_ws_a_tsmom_mop2012.md` | doc-only | Pre-registration doc: "BacktestEngine + governance/validation_stack.py (all 7 gates)" |
| 13 | `graxia/packages/quant_os/tests/test_phase_5_governance.py` | test-legacy | **ONLY live import** (`from governance.validation_stack import ...`) — kept for legacy compat per module docstring |
| 14 | `graxia/packages/quant_os/reports/REPORT_PHASE_5.md` | doc-only | Historical report documenting the module as initially MISSING |
| 15 | `graxia/packages/quant_os/reports/tier1_10_12_tier2_16_22_batch_20260807.md` | doc-only | #18 "DEFERRED — needs user input" entry (superseded by this close) |

## Classification counts
- **live-import:** 0
- **doc-only:** 13
- **packaged:** 1
- **test-legacy:** 1

## Conclusion
No production code imports `governance/validation_stack`. The only code-level consumer is the legacy test `tests/test_phase_5_governance.py` (kept green by design). All other references are documentation/planning/historical or the generated egg-info manifest. Deprecation is safe; the module stays in-tree for legacy test compat but must not be imported by new code.
