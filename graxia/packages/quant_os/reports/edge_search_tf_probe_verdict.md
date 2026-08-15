# Edge Search TF Probe Verdicts + Guard State

**Date:** 2026-08-06
**Source:** Tier 0 sweep Sub-project C — spec `docs/superpowers/specs/2026-08-06-tier0-sweep-design.md` (commit 8f04fa67), plan `docs/superpowers/plans/2026-08-06-tier0-sweep.md` (commit 55b831e7)

## 1. Guard state (2026-08-06, verified)

- get_slice() truncation: ACTIVE (engine.py L597)
- _reset_strategy_class_state(): ACTIVE (engine.py L514), test 7/7 (test_lookahead_regression.py)
- check_data_access(): DEAD API (guard L34, called only from tests, zero production call sites)
- fsck: 12,852 unreachable blobs scanned, 0 hits for scan_for_data_leaks/check_data_access
- H1 (hallucination) SUPPORTED; H2 residual = untracked-never-added only

## 2. check_data_access decision (2026-08-06)

- Decision: **FORMAL-ACCEPT (not wired)** — evidence-based, no ambiguity
- Timing proof: engine run loop `for i in range(1, total_bars)` (engine.py L549) calls `guard.advance()` (L551) BEFORE the wire point; a `check_data_access(i)` call at the proposed L597 position would always evaluate `i > i` = False → tautology, adds zero protection.
- Leak vectors covered elsewhere: class-state vector closed by `_reset_strategy_class_state()` (L514); external-state vector handled by C0.3 AST scan (not runtime-checkable in-process — audit §4 L778-781).
- Consequence: engine.py NOT modified in C0.2. Tests `test_lookahead_detection_wired.py` (2) prove guard API works standalone (strict raise + non-strict allow) — retained as unit tests, not wired into production.
- No flaky-safe run needed: no production code change.

## 3. External-state scan verdicts (2026-08-06)

Scanner: `scripts/scan_external_state.py` (Task C0.3, AST-based; flags file-I/O calls + subscript/attribute reads on non-local/non-imported names inside generate_signal).

| Caller | Verdict | Evidence |
|---|---|---|
| edge_search_tf_probe.py | CLEAN | all strategies read engine-passed args only |
| edge_search_m15_scalper.py | CLEAN | all strategies read engine-passed args only |
| run_ws_a.py | CLEAN | all strategies read engine-passed args only |

TF probe CLEAN detail: calls engine.run() (L138); AsianScalper/HappyGoldScalper generate_signal read ONLY engine-passed args (asian_scalper.py L135-137 close/high/low + current_time L143; happy_gold_scalper.py L126-128 + L134); load_bars() reads CSV BEFORE run() via engine.load_data() = legitimate data channel (engine slices per bar via guard.get_slice() engine L597), NOT the external-state vector.

Tests: tests/test_scan_external_state.py 3/3 (clean → [], file-io → >=1, cache subscript → >=1); verified independently by controller.

## 4. Knowledge Dump correction status (2026-08-06)

- PENDING (Task C2.2) — agentmemory mem_mscs5l95_cb9c96d87786 §6

## 5. mlmr fallback status (2026-08-06)

- PENDING (Task C3.3) — safe_load_ml_model never existed; constant 0.65 fallback; manifest degenerate entry flagged
