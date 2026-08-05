# Design: Release Gate Audit & Record Reconciliation

- **Date**: 2026-08-03
- **Status**: Approved by user (design approved with Trial #2001 stop-gate condition)
- **Owner**: quant_os team (builder agent)
- **Related**: Knowledge Dump (agentmemory `mem_mscs5l95_cb9c96d87786`), `Meta/graxia_mega_plan_v3.md`, `reports/edge_search_cross_sectional_20260720.json`, `scripts/check_candidate_dsr.py`, `validation/n_trials.py`, `quarantine_manifest.json`, `scripts/run_release_gate.py`

## 1. Context & Goals

### Goal
Reconcile 5 independent audit findings from the 2026-08-03 release-gate audit: correct the record where evidence is settled, and add mechanisms where record-fixes have been proven insufficient. One spec, one implementation agent, stream-by-stream.

### Measured facts
- Release gate is GREEN on clean HEAD (committed `2b0b7d0b` main / `80886c63` qo_clean): 3462 passed / 0 failed / 0 errors / 60 skipped, RC 0 × 2 runs, reproducible, seal match.
- Knowledge Dump claims MEGA_PLAN v3 "never existed" — **false**; file exists at `Meta/graxia_mega_plan_v3.md` (root cause: prior subagent ran in /tmp worktrees lacking the file; verified across 6 worktrees).
- Knowledge Dump claims Trial #2001 ran "2005-2018, 12.99 ปี" — contradicts detection logic (regime `crisis=true` requires data ≥2020-04-30 or ≥2022-06-30) and `data/XAUUSD_D1.csv` (data to 2026, committed 2026-07-01). `data_end` is metadata-only (not passed to `run_dk_test`).
- N for multiple-testing has **4 conflicting values**: 1050 (conservative), 1033 (strict) in Knowledge Dump; 1021 (ledger occupancy `trial_ledger.json`, 1021/1022 slots); 1508 (hardcoded in `scripts/check_candidate_dsr.py`). Prior caller-grep task (check_candidate_dsr.py vs n_trials.py) never completed.
- Gate baseline dropped 3639 → 3522 (117 tests) — legitimacy of the disappearance unverified.
- 60 skips approved wholesale via manifest `approved_runtime_skips` (8 reason groups) — legitimacy unverified.
- Quarantine count changed 95 → 35 via counting-rule change (skipped vs ignored_quarantined) — disjointness unproven.
- Single-writer rule (F26) documented but never enforced: 40 dirty files in main working tree from other sessions; unauthorized commits occurred previously; worktree sprawl caused the v3-file false conclusion.
- 27 QOS-RB-* logic failures remain intentionally quarantined — always stated when reporting gate GREEN.

### Success criteria
1. All 5 streams reach their per-stream end state (see matrix).
2. No stream re-opens, re-verdicts, or silently alters a trial verdict or the release gate's green status.
3. Every correction has evidence trail; every mechanism is tested.
4. Knowledge Dump (agentmemory) reflects verified facts only.

## 2. Decision Matrix

| # | Stream | End state | Stop-gate | Acceptance |
|---|--------|-----------|-----------|------------|
| A | MEGA_PLAN v3 dump fix | Record correction only | none | Dump item 6 corrected with path + commit evidence; no code change |
| B | Trial #2001 date range | Evidence + correction | **STOP if rerun/verdict change needed** | Verdict file untouched; dump numbers corrected to evidence or escalation documented |
| C | N reconciliation | Derived single source (mandatory) | none | One N source; no hardcoded duplicates; regression test |
| D | F26 single-writer | Real mechanism | none | Concurrent sessions can't both hold lock; gate fail-closed on foreign lock |
| E | Gate 117 tests + 60 skips | Evidence + correction + guardrail | none | Disappearance explained with git evidence; skips mapped to env conditions; skipped ∩ ignored_quarantined = ∅; baseline diff in gate output |

**Implementation order**: A → B → C → E → D.

## 3. Stream A — MEGA_PLAN v3 Knowledge Dump Correction (record only)

### Evidence
1. File exists (glob-confirmed): `Meta/graxia_mega_plan_v3.md`.
2. Verify git history: `git log --oneline --follow -- Meta/graxia_mega_plan_v3.md` — expect commits `9e6a7421` / `736d5199` (2026-07-04). Record hashes in evidence.
3. Root cause documented: prior subagent's /tmp worktrees lacked the file → false "never existed" conclusion.

### Correction
- Update Knowledge Dump entry `mem_mscs5l95_cb9c96d87786` item 6: file exists at the path above; commits listed; prior "missing" was worktree isolation.
- No mechanism, no code change.

### Acceptance
- Dump item 6 states existence + path + commit evidence. Zero repo file changes.

## 4. Stream B — Trial #2001 Date Range (evidence + correction, STOP-GATED)

### Evidence
1. Open `reports/edge_search_cross_sectional_20260720.json`: read `data_range.end` + run timestamp.
2. Identify which file the official REJECT verdict references (ledger points to trial-1022 file) — compare against the edge_search JSON.
3. Compare with detection logic: regime `crisis=true` requires data ≥2020-04-30 or ≥2022-06-30; `data/XAUUSD_D1.csv` contains data to 2026.
4. Determine which of the two hypotheses holds: (a) stale numbers in Knowledge Dump, or (b) two separate Trial #2001 runs.

### STOP-GATE (hard condition, per user approval)
**If the evidence shows the trial did not run to the required data range (i.e., a rerun with full data would be needed, or any verdict change is implied): STOP the stream immediately and ask the user. Do NOT conclude a new verdict, do NOT re-verify the trial, do NOT re-open it, and do NOT change the verdict file within this spec. Any rerun is a new pre-registered trial, requiring pre-registration first and explicit user approval.**

### Correction (only when no rerun is implied)
- Fix dump numbers ("2005-2018, 12.99 ปี") to match evidence (e.g., correct data range / holdout numbers) — only if the verdict file itself is unaffected.
- If evidence is ambiguous: document findings, leave dump untouched, escalate.

### Acceptance
- Verdict file byte-identical before/after stream (record sha256 in evidence).
- Dump numbers corrected to evidence, OR escalation note written; never both silently.

## 5. Stream C — N Reconciliation (derived single source, mandatory)

### Evidence
1. Complete the unfinished caller analysis: `grep -rn "check_candidate_dsr\|n_trials"` across `scripts/`, `validation/`, `backtest/`, `oracle/`, `micro_live/`, `expansion/`.
2. Enumerate every hardcoded N and every import of `validation/n_trials.py`.
3. Confirm ledger semantics: 1021 = `trial_ledger.json` occupancy (slots used / 1022 capacity), not trials-run count.

### Design
- **Single source of truth**: `validation/n_trials.py` is the only N provider. N = trials actually run, derived from `trial_ledger.json` cumulative count (documented derivation).
- `scripts/check_candidate_dsr.py` imports N from `n_trials.py`; hardcoded 1508 removed.
- Knowledge Dump numbers relabeled to true meanings: 1050 = conservative estimate, 1033 = strict-filter estimate — or corrected to derived value, per evidence.
- Regression test: `check_candidate_dsr` N == ledger-derived N.

### Acceptance
- `grep -r "1508" scripts/ validation/` clean.
- Single import chain for N; no duplicate literals.
- Regression test passes; dump has exactly one N with definition.

## 6. Stream D — F26 Single-Writer Mechanism (real mechanism)

### Evidence
- Working tree currently has 40 dirty files from other sessions (documented pre-existing condition; not a blocker for the mechanism).
- Prior doc-only warnings failed ≥3 times (worktree sprawl, unauthorized commits, 40 dirty files).

### Design
- Repo-root lock file `.writer.lock`: JSON `{owner, pid, timestamp}`. Acquire/release via small script (`scripts/acquire_writer_lock.py`, `scripts/release_writer_lock.py`).
- Pre-flight check in `scripts/run_release_gate.py`: if lock held by another session → gate refuses (fail-closed) with owner info in output.
- Stale-lock handling: lock older than N hours may be cleared only with explicit confirmation (no silent auto-clear).
- Mechanism does not require clean tree to ship.

### Acceptance
- Scripted test: acquire twice → second fails; release → re-acquire succeeds.
- Gate run with foreign lock aborts with owner info (unit-level test, not full 20-min run).
- Procedure documented (one paragraph in spec + script docstrings).

## 7. Stream E — Gate Baseline Integrity (evidence + correction + guardrail)

### Evidence
1. **117 tests**: `git log`/`git diff` on tests between 3639-baseline and 3522-baseline commits → locate the 117. Classify each: legitimate removal (deleted/renamed/deprecated) vs gate-easing. Record per-file counts.
2. **60 skips**: map each of the 8 manifest reason groups to its env condition proof (testcontainers, canary.review missing, _StrategyFailureTracker, DATABASE_URL, multi_provider obsolete, risk_monitoring_ml threads, openssl, warehouse data). Evidence: test code env-gates + reason text.
3. **Quarantine disjointness**: prove `skipped ∩ ignored_quarantined = ∅` — verify no test is both skip-listed and ignored via manifest + pytest collection output.

### Correction
- Findings documented in `artifacts/release_gate/audit_20260803/` (evidence file with per-test classification).
- If evidence reveals illegitimate gate-easing: fix the cause, do NOT re-ease (per Stream E acceptance the gate must stay green on honest counts).

### Guardrail (cheap)
- `summary.json` gains `baseline_diff` (`passed`/`skipped` delta vs previous run).
- Gate prints `RE-BASELINE DETECTED: passed +N / skipped −N` when counts shift from previous run.
- No refactor; additive only.

### Acceptance
- Evidence file lists all 117 (removed vs legit, with git hashes) and all 60 skips (reason → env condition proof).
- Disjointness proven in evidence.
- `baseline_diff` present in next gate run output.

## 8. Edge Cases & Decisions

| # | Edge case | Decision |
|---|-----------|----------|
| E1 | Trial #2001 evidence shows incomplete run | **STOP + ask** (Stream B stop-gate). No verdict change, no rerun, no pre-registration bypass. |
| E2 | Evidence ambiguous for Trial #2001 | Document findings, leave verdict + dump untouched, escalate to user. |
| E3 | Another hardcoded N found beyond 1508 | Include in reconciliation; all literals must route through `n_trials.py`. |
| E4 | Lock file left stale after crash | Manual confirmation required to clear; never auto-clear silently. |
| E5 | 117 tests include real removals (renamed/deprecated) | Legitimate; document with hashes. Only flag gate-easing if tests were deleted to raise pass counts. |
| E6 | 60 skips include a mislabeled bug | Un-skip the test (remove from approved list) and treat as real failure — do not keep hiding it. |
| E7 | Another session holds the gate lane mid-stream | Respect single-writer: wait or coordinate; never commit over foreign lock. |
| E8 | Full gate runs are ~20 min each | Only one full run needed for baseline_diff guardrail demonstration; other streams verified by targeted tests. |

## 9. Verification Plan
- Stream A: `git log --oneline --follow -- Meta/graxia_mega_plan_v3.md` output recorded; dump read-back confirms correction.
- Stream B: sha256 of verdict file before/after; evidence JSON fields recorded.
- Stream C: targeted pytest for N regression; grep for `1508` clean.
- Stream D: lock acquire/release test; gate pre-flight unit test (foreign lock aborts).
- Stream E: evidence file with all 117 + 60 classifications; one full gate run (optional, ~20 min) to show `baseline_diff` in output.
- Full `tests/` regression run before merge (per repo guidelines) when any source/script change lands (Streams C, D, E touch code).

## 10. Out of Scope / Constraints
- No changes to `CONSTITUTION.md` invariants.
- No pre-registration bypass for any trial rerun.
- No silent re-verdict of any trial (Stream B hard gate).
- Quarantine manifest discipline preserved: any skip-list change committed with justification.
- Never present audit/reconciliation results as live-profit proof.
