# Tier 0 Sweep — Design (Sub-projects A/B/C + Component 0)

**Date:** 2026-08-06
**Status:** APPROVED by user (sections 1–3 reviewed; Section 2 fixes incorporated; Section 3 corrections incorporated)
**Applies to:** quant_os master open-items checklist (Tier 0 items) — decomposed into 3 sub-projects + a new Component 0.

---

## 1. Problem

The master open-items checklist (`QUANT_OS_MASTER_OPEN_ITEMS.md`, committed `b362cdbe`) lists 8+ Tier 0 items. Investigation revealed several claims in that checklist are **stale or wrong** — including its own storage (the file is NOT on disk in the current branch), the `scan_for_data_leaks` "P0 GAP" framing, the #2 collision status, and the Direction G Step 1 "in progress" status. This design sweeps those items to ground truth with evidence, no hype, no overclaim.

## 2. Current State (verified evidence, 2026-08-06)

### 2.1 Checklist file
- Committed at `b362cdbe` (121 lines) but **NOT on disk** in current branch (`git diff b362cdbe..HEAD` = 121 deletions; glob empty; HEAD on `review/rydc-atr-pnl-honesty` then moved to `c0175e91`).
- Canonical "evergreen" tracker is invisible to the working tree → must be restored + refreshed.

### 2.2 #14 — `scan_for_data_leaks()` archaeology (this session, direct commands)
| Command | Result |
|---|---|
| `git log --all -S "scan_for_data_leaks"` | Only 2 commits, both DOCS (`f69a0f43` status doc, `b362cdbe` checklist). Zero code commits on any branch. |
| `git status -- core/lookahead_guard.py` | Clean — committed state = disk state. |
| `git stash list` (via `.git/logs/refs/stash`) | **7 stashes** (checklist said 13 — stale count). None contain it (`--all` covers refs/stash in -S search). |
| `git worktree list` (via `.git/worktrees`) | **18 worktrees** (checklist said 13+ — stale count). None hold it. |
| grep `.py` for `scan_for_data_leaks` | Zero matches on disk. |
| `git fsck --lost-found` | **Blocked by permission rules** — not runnable in this environment. |

**Current runtime protection (direct read of `engine.py` + commit `2820df99`):**
- `get_slice()` truncation — ACTIVE, engine.py L597, every bar (argument channel).
- `_reset_strategy_class_state()` — ACTIVE, L514, added 2026-07-30 in `2820df99` (closes class-level `_full_data_ref` CheatingStrategy vector), tested 7/7 in `tests/test_lookahead_regression.py`.
- `check_data_access()` — exists (guard L34) but **dead API**: called only from tests, zero production call sites.

**Key distinction (3 levels, kept separate):**
1. **Class-state vector** — closed at runtime by `_reset_strategy_class_state()` (verified, tested).
2. **Detection channel** — dead (`check_data_access` never wired). Decision needed.
3. **External-state vector** — architecturally unblockable in-process (file/live-cache reads in `generate_signal`); audit §4 L778-781 documents this. Needs code-review/lint-level check, applies to ALL existing `engine.run()` callers.

**Hypothesis status — TWO hypotheses held as live (not resolved):**
- **(H1) Hallucination:** doc-18 fabricated the report (test counts, methodology) with no real code.
- **(H2) Destroyed-uncommitted-work:** doc-18 staged real work; a parallel session's `reset --hard`/`checkout` wiped it pre-commit (leaves no log/stash/worktree trace).
- Evidence currently **cannot distinguish** them: `.git/objects/pack/` shows a repack ran **2026-08-06 01:45** (pack-1a6f9427, 660MB) — any unreachable loose blob from H2's staged state would have been pruned. Which worktree/branch doc-18 originally used is ALSO unknown/time-decayed (index-level staged state is not branch-persistent). **Both hypotheses stay live in all outputs.**
- `2820df99` full message read: independently root-causes the CheatingStrategy vector, adds `_reset_strategy_class_state` under a different name, references NO prior `scan_for_data_leaks` work → supports **uncoordinated-parallel-session** pattern, not hallucination confirmation.

### 2.3 #2 — Trial #4002 collision
- Incident report (`reports/incident_20260805_trial_4002_collision.md`) says **CLOSED 2026-08-05, NO-ACTION-REQUIRED**: offending record was working-tree-only, never committed, `check_trial_uniqueness.py` passes 63 entries / 0 collisions.
- Checklist (written 2026-08-06) says "decision not yet made" — **contradicts its own incident report**. Correction needed.
- Root cause (parallel session writing trial-numbered records to main ledger without checking direction-owned ranges) remains a live risk — hardener (#19/#17) stays open.

### 2.4 #3 — Main-ledger cap anomaly
- `research/trial_ledger.json` L6-8: `cumulative_trial_cap: 1022`, `lock_doc_path: reports/stopping_rule_2026_07_12.md` — stale.
- `scripts/auto_increment_trial.py` L40 references `stopping_rule_2026_07_30.md §3.1` (cap 1042) — the two disagree.
- Decision pending: revert-and-separate vs leave-as-is (user decision, Sub-project B).

### 2.5 #4/#15 — Direction G — **STOPPED (critical new finding)**
- `reports/stopping_rule_2026_08_05.md` L78-102: **3 consecutive REJECTs triggered §4.4 stop on 2026-08-06** (8001 BTCUSD H1 Donchian 1,391 trades REJECT; 8002 EURUSD M15 London breakout 20 trades REJECT; 8003 BTCUSD D1 TSMOM+YZ 3 trades REJECT). Confirmed by commit `f5e4df1e` (2026-08-06 00:46).
- **Step 1 sampler never ran:** `data/spread_measurements/` does not exist; `.step1_sampling.lock` absent; **no code anywhere creates the lock** (grep .py/.ps1/.md); no setup script registers task `quantos_step1_spread`; `step1_sampler.py` L68-70 refuses to run without the lock → precondition unmeetable by codebase.
- Coverage files stale since 08-05 (`had_gap: true`, `covered: false`); heartbeat.txt (written by `core/orchestrator.py`, NOT the measurement daemon) showed 02:20 local — orchestrator alive, sampler not.
- **NFP 2026-08-07 window is MOOT** for Direction G — the direction is formally stopped. EURUSD H4 (TF probe gross Sharpe 3.46) would need a new stopping-rule doc (Direction H) + user decision before pre-registration.
- Scope of C1 reduced accordingly: **no MT5 re-measure** — evidence-based reclassification only. This is an EXTERNAL-event scope reduction (Direction G stop), NOT a team decision; user can re-evaluate.

### 2.6 #5 — `tradeable_universe.json` contradiction
- EURUSD/GBPUSD in BOTH `measuring` (L56/62) AND `excluded` (L332/336, reason "No cost data").
- Evidence: `cost_calibration.json` L200-298 has REAL data — EURUSD (FROM_TICKS, 56,115 ticks, 4.42 days, round_trip 14.17 bps, window 2026-07-31→08-05, mt5_copy_ticks_range_backfill); GBPUSD (FROM_TICKS, 214,512 ticks, BUT measurement_window "24h tick parquet (2026-06-25)", measurement_duration_days 1, mode tick_parquet, note "SP3: calibrated from existing 24h tick parquet" — **weaker evidence**).
- `excluded` reasons are stale ("No cost data" false).

### 2.7 #6 — Knowledge Dump false claim (3 locations)
- agentmemory `mem_mscs5l95_cb9c96d87786` (2026-08-03) claims "MEGA_PLAN v3 draft ไม่เคยมีอยู่จริง" — FALSE, file exists at `Meta/graxia_mega_plan_v3.md` (git commits 9e6a7421/736d5199).
- Files on disk with same false claim: `MEGA_PLAN_v2_Quant_OS_Live_Readiness.md` L15/L51, `plan.md`.
- All 3 must be fixed (memory entry + 2 files).

### 2.8 Reciprocal supersession (F25 debt)
- `MEGA_PLAN_v2` L51: CHANGE_CONTROL.md + LIVE_TRADING_READINESS_MASTER.md "still needs a note, not yet added" (07-28).
- `plan.md` L88/L198 say chain "fully understood" — analysis only, notes never written.
- **Notes were never added — not duplicate work.** C2 adds them.

### 2.9 C3 evidence anchors
- **KhubievPortfolio:** `strategies/khubiev_portfolio.py` L160-161 (`fit_on_init=True`, `train_fraction=1.0`), test L518 uses `fit_on_init=False`; audit §6.2. Inert — no trial uses it (grep verified).
- **Trial 1028:** `scripts/run_ws_a_tsmom.py` L202/L224 same-bar fill; signal L191; `dk_t=0.428` conservative; registry L493.
- **mlmr:** `safe_load_ml_model` never existed (audit §8.1) → silent constant 0.65 fallback; `ml/models/manifest.json` XAUUSD `z_score: 31.8` + degenerate confusion matrix `[[0,68115],[0,80305]]`.

### 2.10 Checklist metadata corrections (recorded)
- Stash count: **13 → 7** (actual). Worktree count: **13+ → 18** (actual). HEAD branch mid-investigation: `review/rydc-atr-pnl-honesty` → `c0175e91` (reason unknown — open question, not blocking).

---

## 3. Decomposition (user-approved)

Three sub-projects + one new component:
- **Sub-project A** — Verification: #1 (trial 2001/1022 date range), #46 (doc-18 re-audit).
- **Sub-project B** — Decisions: #2 (collision — already closed per incident, confirm), #3 (cap anomaly), + NEW: "open Direction H for EURUSD H4?" decision.
- **Sub-project C** — Fixes: #5 (universe), #6 (Knowledge Dump), #14 sub-gaps, + **Component 0** (runtime guard truth-up).

This spec covers **Sub-project C** (largest). A and B are tracked as separate specs/plans per decomposition.

---

## 4. Design — Stream C0 (NEW): Runtime guard truth-up

### 4.1 Scope
1. Verify current protection state on the landing branch (forward safety — NOT archaeology closure; archaeology is unresolvable per §2.2).
2. Decide `check_data_access` fate — **auto-rule with explicit threshold, gray zone escalates to user** (see §8.1).
3. External-state scan of existing `engine.run()` callers — **different vector than `check_bypass_loaders.py`** (that checks bypassing the engine entirely; this checks callers that pass gates but read file/live-cache state inside `generate_signal`). Reuse AST-scanning *methodology*, NOT the script itself.
4. doc-18 re-audit with 7-channel methodology → verdict table, **both-hypotheses note** (no single-answer assertion).

### 4.2 Data flow
Per-caller verdict list → decision → wiring or formal-accept → checklist update.

### 4.3 Error handling
Fail-closed: no evidence → no status change. Wiring risks runner breakage → fallback formal-accept with audit doc.

### 4.4 Testing
- `test_lookahead_regression.py` 7/7 must stay green.
- New test for any wiring change.
- **81/81 from 2820df99 scope stays green** (this is C0, NOT C3).

## 5. Design — Stream C1: Universe truth-up (scope reduced)

### 5.1 Scope (external-event reduced)
Direction G stopped → **no MT5 re-measure** in this sub-project. Evidence-based reclassification only. User's "maximal evidence" intent documented as reduced by external event, not team choice; re-evaluable.

### 5.2 Decision rule for EURUSD/GBPUSD status
Borrow Direction G Step 1 sampling standard (>=1500 samples/symbol over multi-day window):
- **EURUSD** (FROM_TICKS, 56,115 ticks, 4.42 days, mt5_copy_ticks_range_backfill) → **MEETS** → `measuring` (provisional, per prior precedent).
- **GBPUSD** (FROM_TICKS tick count 214,512 BUT window "24h tick parquet (2026-06-25)", duration 1 day, mode tick_parquet) → **DOES NOT MEET multi-day threshold** → **`excluded` with evidence note** ("single-day 2026-06-25 parquet; re-measure required under any future Direction H sampling").
- `excluded` stale reasons replaced with accurate evidence strings.
- Remove dual membership — one status per symbol.

### 5.3 Acceptance
- `tradeable_universe.json`: EURUSD/GBPUSD resolved — one status each; reason strings match cost_calibration.json evidence.
- Evidence report: calibration source, tick counts, window, mode per symbol; GBPUSD weak-evidence note preserved.
- `require_cost_calibrated()` gate still passes on tradeable symbols after edit.

## 6. Design — Stream C2: Knowledge Dump + supersession

1. Fix 3 false-claim locations: agentmemory `mem_mscs5l95_cb9c96d87786` §6, `MEGA_PLAN_v2` L15/L51, `plan.md`.
2. Add reciprocal supersession notes to `CHANGE_CONTROL.md` + `LIVE_TRADING_READINESS_MASTER.md` (verified never written).
3. Acceptance: grep confirms zero remaining "MEGA_PLAN v3 draft never existed" false claims in .md files.

## 7. Design — Stream C3: 4 sub-gaps

1. **KhubievPortfolio** L160-161: fail-closed default (refuse full-history fit or require explicit opt-in). New test proves default path cannot leak.
2. **Trial 1028 ledger footnote**: headline Sharpe from zero-lag engine, optimistic; REJECT unchanged (dk_t=0.428 conservative).
3. **External-state lint**: scans existing callers (reuse C0 artifact) + guards new strategy code. Test proves a file-reading strategy is flagged.
4. **mlmr fallback**: fix to real signed-load OR make explicit constant-fallback with warning (documented security tradeoff per audit §8.1). Flag `ml/models/manifest.json` degenerate entry with doc.

---

## 8. Acceptance Criteria (cross-stream)

### 8.1 C0 guard decision rule (auto with gray-zone escalation)
- **Wire** `check_data_access` into `BacktestEngine.run()` as load-bearing detection **IF AND ONLY IF**: full-suite pass rate does not decrease vs baseline (relative threshold — suite is 3,500+ tests, absolute "<=2" has no meaning without knowing WHICH tests), AND `test_lookahead_regression` 7/7 stays green, AND any broken test is one that the C0 external-state scan flagged as vector-related.
- **Formal-accept** if wiring breaks non-vector tests OR cannot be done without risk.
- **Gray zone** (ambiguous breakage, scan uncertainty) → user decision, escalated not auto-decided.

### 8.2 C0 external-state scan verdicts
- Every `engine.run()` caller gets an explicit verdict: **CLEAN** or **VECTOR_FOUND** — not just "in per-caller list".
- **TF probe verdict: CLEAN** — verified this session: `edge_search_tf_probe.py` calls `engine.run()` (L138) with `strategy_for()` mapping (L146-149: XAUUSD→HappyGoldScalper, else→AsianScalper); both `generate_signal` implementations read ONLY engine-passed args (`asian_scalper.py` L135-137 close/high/low + current_time L143; `happy_gold_scalper.py` L126-128 + L134), no file/live-cache/class-container reads. `load_bars()` (probe L83-96) reads CSV but BEFORE run() via `engine.load_data()` — legitimate data channel (engine slices per bar via `guard.get_slice()` engine L597), NOT the external-state vector.

### 8.3 C1 universe
- Per §5.2 rule. EURUSD → measuring (provisional); GBPUSD → excluded with evidence note.

### 8.4 Checklist refresh (all streams)
- `QUANT_OS_MASTER_OPEN_ITEMS.md` restored to disk + updated: #14 reclassified (3-level, both-hypotheses), #2 corrected to "CLOSED no-action", #3 flagged, stash-count 13→7, worktree-count 13+→18, Direction G STOPPED + sampler-never-ran, HEAD-branch observation, #4/#15 reclassified, #5 status per C1 rule.

---

## 9. Edge Cases
- **Repack timing:** future `git gc` during work → evidence snapshots taken before (stashes/worktrees/packs already captured).
- **Universe dual-write race:** another session edits `tradeable_universe.json` mid-fix → single-writer lock (reuse `.writer.lock` pattern from `run_release_gate.py`, no new mechanism) or fail-closed merge check.
- **agentmemory API drift:** `mem_mscs5l95_cb9c96d87786` missing/read-only → record correction in new memory entry + file corrections carry truth.
- **Khubiev live usage:** grep confirmed no trial uses khubiev — inert; but re-verify before changing default.
- **mlmr silent fallback:** if signed-load infra unavailable → explicit constant-fallback with warning (documented tradeoff).
- **Concurrent-session branch moves:** HEAD moved mid-session (c0175e91) — path-scoped commits, verify branch before each commit.

---

## 10. Rollback
- All streams doc/config/memory + small guarded code fixes — revert = `git revert` per commit or manual JSON restore.
- C0 wiring: revert wiring commit only if it breaks non-vector tests; formal-accept path continues.
- No locked experiment outputs touched (CONSTITUTION.md invariant).

---

## 11. Open Questions (recorded, non-blocking)
1. **HEAD branch reason:** HEAD was on `review/rydc-atr-pnl-honesty` mid-investigation, now `c0175e91` — intentional switch or parallel session? Governance-log item only; check reflog/ask. Does NOT block any stream.
2. **fsck:** blocked by permission rules + repack pruned 2026-08-06 01:45 — H1 vs H2 unresolvable via git. Held as both-live in all outputs.
3. **Direction H decision:** EURUSD H4 pre-registration requires new stopping-rule doc + user decision (Sub-project B decision list). MT5 sampling would return with it — no separate sub-project now.

---

## 12. Risks
- **Medium:** C0 wiring touches every `engine.run()` caller (TF probe, runners). Mitigated by relative threshold + gray-zone escalation + revert-per-commit.
- **Low:** C1/C2/C3 are doc/config/memory changes with per-file evidence.
- **Low:** Direction G stop is a methodology-correct outcome (pre-registered rule fired) — not an error to fix.
