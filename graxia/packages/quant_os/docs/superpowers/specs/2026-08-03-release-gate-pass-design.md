# Design: Release Gate Pass — Rolling Re-enable of Quarantined Tests

- **Date**: 2026-08-03
- **Status**: Approved by user (all sections approved)
- **Owner**: quant_os team (builder agent)
- **Related**: `quarantine_manifest.json` (35 entries), `scripts/run_release_gate.py` (config 3639/3639), QOS-RB-001..032

## 1. Context & Goals

### Goal
The release gate (`scripts/run_release_gate.py`) must go **GREEN**: every check passes, 0 quarantined tests, reproducible, auditable.

### Measured facts
- Gate config is fail-closed:
  - `required_collected_tests: 3639`, `required_passed_tests: 3639`
  - `allowed_failed_tests / errors / xfailed / xpassed / timeouts: 0`
  - `allowed_unapproved_skips: 2`
  - `required_reproducibility_runs: 2`, `required_equal_ledger_seal_hashes: True`
- Quarantine manifest: 35 entries (QOS-VWAP-001, QOS-ORDERFLOW-001, QOS-MT5E2E-001, QOS-RB-001..032). Already staged with 35/35 `--ignore=` lines in SUITE_CMD; manifest↔gate consistency verified (script: `verify_manifest.py`, all green).
- **The gate cannot pass while quarantined**: `required_collected_tests: 3639` requires every test collected AND `required_passed_tests: 3639` requires every test passed. Each `--ignore` reduces the collected count below 3639 → gate fails. Quarantine is transitional, not terminal.
- Working tree: 23 modified files (≈15 are the other session's live source fixes, 2 are the staged gate pair, rest are churn/evidence), 8 untracked (scratch + hook outputs).
- `artifacts/release_gate/` is empty — no gate-run baseline exists yet.

### Success criteria
1. Gate exits 0 with all checks green.
2. Manifest `total_quarantined` ends at the true terminal state (0 or only genuinely environment-gated entries).
3. Every batch re-enable has artifacts evidence under `artifacts/release_gate/`.
4. Tree is clean at gate run time (churn gitignored, evidence committed, scratch moved out).
5. Two reproducibility runs with equal stats and equal ledger seals.

## 2. Tech Approach — Rolling Re-enable (Approach C, user-selected)

### Phase 0 — Preparation
1. **Clean-tree prep**:
   - Add to `.gitignore` (pure churn): `data/heartbeat.txt`, `data/kill_switch_state.json`, `tests/.test_tmp/`, `data/visual_index/quant_meta.json`, `data/manifests/XAUUSD_D1.manifest.json`.
   - Keep tracked (evidence): `state/audit_log.jsonl`, `validation/.experiment_registry.json` — commit when changed.
   - Move scratch to `C:\Users\menum\AppData\Local\Temp\opencode\`: `commit1.txt`, `commit2.txt`, `pytest_verify.txt`, `sanity_post.txt`, `precommit_out3-6.txt`, `CLAUDE.md` (untracked).
   - `run_release_gate.py` is `MM`: keep the staged re-baseline; review and keep the other session's unstaged `parse_pytest_output` fix (reverse-scan; correct).
2. **Failure baseline**: run the suite ONCE with current 35 ignores → `artifacts/release_gate/baseline/` (collected, skipped, passed counts). Ground truth for config recalibration.
3. **Config recalibration** (from baseline only, never speculative):
   - If baseline shows real skips (test_vwap deprecated, test_engine_ledger_tamper multi-trade), `required_passed_tests` must be `3639 − actual_skips` (max possible passed). Record justification.
   - If skips = 0, keep 3639.
   - `required_collected_tests` must equal measured collected at terminal state; must satisfy `collected == passed + failed + errors + skipped`.
4. **Commit the staged pair** (manifest + gate re-baseline + parse fix + config calibration) as its own atomic commit BEFORE batching starts — protects against the other session's pathspec-less commits sweeping them mid-batch (E8).

### Phase 1..N — Batch re-enable loop
For each batch (5–10 files, ordered from QOS-RB-001..032 by standalone-pass likelihood):
1. **Verify each file standalone** (`pytest <file> -q` from repo root). A file that fails standalone is NOT un-ignored — regardless of cause. If the other session's source fixes are not committed yet, wait (Q3).
2. Remove the file's `--ignore=` line from SUITE_CMD and its entry from the manifest; update `total_quarantined`.
3. **Commit the pair atomically** (gate script + manifest in ONE commit — `check_quarantine_consistency` compares `skipped + ignored` vs `total_quarantined`; a split commit breaks it).
4. Run the full suite → green: next batch. Red: fix within batch only; evidence in `artifacts/release_gate/batchN/`.

### Phase Final — Terminal state
1. `total_quarantined` = true terminal count (0 if all 35 pass; keep entry only for genuinely environment-gated files that must stay ignored, e.g. live-MT5 e2e).
2. Full gate run × 2 (reproducibility) → equal stats + equal ledger seals.
3. Commit final state; `artifacts/release_gate/final/` shows all-green.

### Invariants
- **Atomicity**: manifest + gate script committed together, always.
- **No-touch rule**: never modify the 35 test files themselves (other session's lane); only gate ignore list + manifest entries.
- **Ordering**: batching starts only after the other session's source fixes land and per-file standalone verify passes.
- **Evidence**: every run writes `artifacts/release_gate/<label>/` (built into `run_suite`: git_commit.txt, python_version.txt, lockfile_sha256.txt, pytest_command.txt, pytest_output.txt, test_result.json, e2e_output.txt).

## 3. Edge Cases & Decisions

| # | Edge case | Decision |
|---|-----------|----------|
| E1 | Other session never finishes / commits late | Wait, do not steal the lane. Standalone per-file verify is the hard gate before any un-ignore. Pause + ask if blocked long. |
| E2 | `allowed_unapproved_skips: 2` vs `passed >= 3639` tension | `required_passed_tests` = baseline-measured passed at terminal state (3639 − actual skips) with justification in commit. Config changed only after baseline measurement. |
| E3 | Consistency check with 0 quarantine but skips > 0 | Manifest stays source of truth: keep manifest entry for genuinely-skipped files (count matches) or eliminate skip markers. Determined at baseline. |
| E4 | Legacy entries (VWAP/ORDERFLOW/MT5E2E) | Not auto-un-quarantined like RB entries. Re-enable only if they pass standalone here; else keep entry + `--ignore`, and `required_collected_tests` accounts for them. |
| E5 | CRLF churn (.github/workflows/ai-code-review.yml, check_bypass_loaders.py, validate_dtsmom_strategy.py) | Verify whitespace-only with `git diff --stat` before touching. Candidate `.gitattributes` (`* text=auto`) if churn persists. |
| E6 | Other dirty source files not in classification (data/quality_gate.py, core/tv_integration.py, core/agents/llm_router.py, gold_bot/core/risk_bridge.py, canary/demo_canary_config.py, observability/opik_tracer.py, .mcp.json) | Leave untouched (other session's active edits). Exclude from my commits. Revisit at final gate run; if still dirty → ask. |
| E7 | Gate runtime ~20min/run; ~8–10h worst case for all runs | Acceptable; batches ordered by standalone-pass likelihood to minimize red runs. Runs are subprocess-based; monitor. |
| E8 | Other session's pathspec-less commit sweeps my staged pair | Commit my pair at Phase 0 completion (before batching) as its own atomic commit. |

## 4. Verification Plan
- Baseline run before any config change (evidence: `artifacts/release_gate/baseline/`).
- Standalone `pytest <file> -q` per file before un-ignore.
- Full suite run after every batch commit.
- Final: `python scripts/run_release_gate.py` × 2, both green, seals equal.
- Manifest↔gate consistency re-verified after every batch (rerun `verify_manifest.py` logic).
- `git status` clean at final run (except allowed evidence commit).

## 5. Out of Scope
- Modifying the 35 quarantined test files themselves (other session's lane).
- Changes to `CONSTITUTION.md` invariants.
- Backtest/demo results presented as live-profit proof (per repo rules).
