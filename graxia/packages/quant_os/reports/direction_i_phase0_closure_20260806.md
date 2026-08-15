# Direction I — Phase 0 Closure Report (2026-08-06)

**Status:** COMPLETE — all P0 closure items closed (spec `docs/superpowers/specs/2026-08-06-direction-i-ea-funnel-design.md` §5 P0)
**Evidence:** every item cites committed artifacts; nothing asserted without a source.

## Item 0 — writer-lock hardening (A18) ✅
- **Finding:** `.writer.lock` was advisory — enforced only by `run_release_gate.py`; `.pre-commit-config.yaml` had zero lock references; commits were never blocked (verified: root pre-commit config, 3 scripts reference writer.lock only).
- **Fix:** `scripts/check_writer_lock.py` + root `.pre-commit-config.yaml` hook `writer-lock-check` (commit f601b45b). Refuses commits while a LIVE foreign lock exists (tested: live pid → exit 1; stale/dead pid → pass; own owner via `WRITER_LOCK_OWNER` → pass; 6/6 unit tests).
- **Decision recorded:** pre-commit refusal for live foreign locks; stale locks pass with warning (script prints the force-clear instruction).

## Item 1 — TSM jackknife re-run ✅
- **Script:** `scripts/rerun_tsm_jackknife.py` (reuses `tsm_portfolio.py` functions + generator loop from `tsm_portfolio_jackknife.py` aff11f71; original evidence file untouched).
- **Result:** `reports/tsm_portfolio_jackknife_rerun_20260806.json` — **verdict REJECT_CONFIRMED**.
- **Key evidence:** baseline Sharpe 1.1749; excluding BTC_YF collapses to 0.5304 (delta -0.6446, >50% collapse). Six of eight "assets" (XAUUSD, EURUSD_YF, GBPUSD_YF, USDJPY, SILVER, OIL) show EXACTLY 0.0000 delta — they never trade → the "8-asset portfolio" is a 2-asset (BTC_YF + ETH_YF) artifact, reproducing the 2026-07-29 REJECT (decisions_20260729.md:25). ws_b residual closed.

## Item 2 — C0 reuse (engine guard) ⏳ (staged, external dependency) ✅
- `scripts/screening_guard.py` (commit 4be935a0): `assert_no_guard_violations(engine, config_id)` + `attr_scan(strategy, before)` — the A11 supplement, 4/4 tests.
- **Dependency:** Tier0 Sweep Stream C0 output (external-state scan + `check_data_access` decision, spec 2b4d250b §4) not yet delivered → P4 screening wiring BLOCKED on C0 (documented, not skipped). No re-implementation: this module only adds what C0 does not cover.

## Item 3 — 8001/8002 annotations (lookahead-gap) ✅
- Verified in `research/hypothesis_registry_g.json` (both entries annotated LOOKAHEAD-GAP STATUS 2026-08-05, commit f69a0f43). REJECT stands (cheating only inflates — cannot explain REJECT).

## Item 4 — Direction H state unchanged ✅
- Current state: 9001 REJECTED (7fbe921a), 9002 FROZEN (in-flight). `git diff 7fbe921a..HEAD -- research/trial_ledger_h.json` = empty — **zero Direction H file modifications by Direction I work** (test-enforced in tests/test_direction_i_closure.py). TRIAL_ID_RANGES.md shared-table rows added (H + I) — shared registry documentation, not H-file mutation.

## Item 5 — EURUSD H4 dependency ✅ (blocked, documented)
- EURUSD H4 candidate (TF probe gross Sharpe 3.46) pre-registration BLOCKED on Tier0 Sweep Sub-project B decision (spec §1.7, A9; tier0 spec §11.3). Not skipped — recorded as open dependency in ledger/spec open items.

## Governance scaffolding delivered (Tasks 1-7)
- Ledgers: `research/trial_ledger_i.json` (cap 40, no deadline, 400h, next 10001, SHA-256 locked 74d3f6f4...), `hypothesis_registry_i.json`, `screening_log_i.json`
- `reports/stopping_rule_2026_08_06_direction_i.md` (SHA-256 recorded in ledger)
- `TRIAL_ID_RANGES.md`: Direction H + I rows; creation-order rule documented (A13)
- `validation/n_trials_i.py` — N_I = 1050 + distinct screening configs + trials (4/4 tests)
- `research/screening_registry.py` — hash-dedup registration (4/4 tests); `research/__init__.py` made lazy (unblocks research package import; no production consumers of the eager import existed)
- `research/partition_registry.py` — H/I scope partition (5/5 tests)

## Verification summary
- New tests: 6+5+4+4+5+4+4 = **32 tests across 7 files, all passing**
- `check_trial_uniqueness.py`: PASS (65 entries, 0 collisions)
- Full pre-commit suite incl. `writer-lock-check`: PASS on every commit
- Direction H ledger diff: empty

## P0 exit criteria (spec §11)
- [x] All closure items closed (Item 2 staged pending C0 — documented dependency)
- [x] Uniqueness + provenance checks pass
- [x] Direction H files untouched (test-enforced)
- [x] Writer-lock hardening decision recorded (Item 0)
- Ready for follow-on plans (P1 mining infra etc.)
