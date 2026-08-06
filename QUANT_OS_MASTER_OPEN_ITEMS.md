# quant_os — Master Open Items Checklist

**Generated:** 2026-08-06 (content origin) | **Canonicalized:** 2026-08-06 (repo root, evergreen)
**Purpose:** Single consolidated list of everything outstanding across every thread discussed to date. Use this to prevent re-discovering the same gaps in future sessions.

> **Canonical location:** repo root `QUANT_OS_MASTER_OPEN_ITEMS.md` (evergreen — update in place; git history preserves versions).
> **Relationship to other plans:** this file is the project-wide master TRACKER. It supersedes the "master plan" role of MEGA_PLAN v2 / Full Remediation & Wiring Plan / QUANT_OS_MASTER_REMEDIATION_PLAN_v6 for *open-items tracking* — those remain canonical for their specific scope (e.g. live-readiness). Follow the supersession pattern already used for `CHANGE_CONTROL.md` / `LIVE_TRADING_READINESS_MASTER.md` (see #16, #17).
> ⚠️ This document is subject to the single-writer/worktree risks discussed throughout — verify it's being read/edited from the correct location before trusting it as current (it was pasted into a session while NOT existing on disk on 2026-08-06 — see "Canonicalization history" below).

---

## Canonicalization history (2026-08-06)

- **2026-08-06:** First created on disk at repo root (was previously a phantom — pasted in-session, no file existed). Corrections applied with verified evidence:
  - #6: MEGA_PLAN v3 **exists** (git log + worktree investigation, 2026-08-05) — old "never existed" claim removed.
  - #13: TF probe corrected — probe calls `BacktestEngine.run()` (it is NOT a loader bypass); cost gate added (commit `03a86dc7`).
  - #14: **UPGRADED to Tier 0** — 7-channel archaeology proves `scan_for_data_leaks()` exists nowhere recoverable; P0 GAP (see item).
  - #15: gated status recorded (commit `03a86dc7`, `break_even_mult=null`, `blocked_on`).
  - #22: verification upgraded from "syntax only" to "behavioral PARTIAL" (1 sync OK at 13:38 post-fix; 5 later starts without completion).
  - NEW #45 (Tier 0): gap-period GO-family verdict audit — #4001/#4002 flagged.
  - NEW #46 (Tier 2): full doc-18 claim re-audit pending.
- **2026-08-06 (Tier 0 sweep C0-C4 executed):**
  - #2: corrected to CLOSED no-action (incident report 2026-08-05 — record was working-tree-only, never committed; check_trial_uniqueness passes 63+/0)
  - #3: BLOCKING flag + immediate pure-data fix noted (lock_doc_path + cap fields stale vs 07_30 doc); deeper revert-vs-separate decision still in Sub-project B
  - #4: Direction G STOPPED (§4.4, 2026-08-06, 3 consecutive REJECTs 8001/8002/8003); Step 1 sampler NEVER ran (no code creates .step1_sampling.lock, no setup script registers quantos_step1_spread); NFP 2026-08-07 window MOOT
  - #5: RESOLVED (commit cd0f4983) — EURUSD/BTCUSD → measuring, GBPUSD/US30 → excluded w/ evidence; universe truth-up report reports/universe_truth_up_20260806.md
  - #14: RECLASSIFIED — 3-level distinction (class-state vector CLOSED via _reset_strategy_class_state 2820df99; detection channel DEAD check_data_access FORMAL-ACCEPT e518d095; external-state vector handled by C0.3 scanner cec6c91c); fsck 12,852 unreachable blobs scanned 0 hits → H1 (hallucination) SUPPORTED, H2 residual = untracked-never-added only
  - #46: PARTIALLY ANSWERED — re-audit done (reports/doc18_reaudit_20260806.md 8a1b046b): H1 supported, H2 residual
  - Stash count corrected 13→7 (actual); worktree count 13+→18 (actual)
  - Checklist metadata: HEAD branch moved review/rydc-atr-pnl-honesty → c0175e91 → multiple (concurrent sessions active — verify branch before every commit)
- **2026-08-06 (Sub-project B decisions):** #2 CLOSED+HARDENED (range-ownership check 8b9c6e20 caught #4004 in MAIN → moved to registry_d, 6d7562f3); #3 RESOLVED (cap 1042 + next 1034, 7b9990e4 — unblocks auto_increment for ALL directions); Direction H opened by parallel session (stopping_rule_2026_08_06_direction_h.md, forex4 scope) + EURUSD H4 pre-registered as 9003 (1b2c1998)

---

## 🔴 TIER 0 — Blocking, high consequence, do first

| # | Item | Status | Why it blocks |
|---|---|---|---|
| 1 | **Trial #2001/1022 date range** — Knowledge Dump claims "2005-2018, 12.99 ปี" but earlier investigation proved `data_range.end=2018` is pure metadata that doesn't gate the actual computation, and CSV data goes to 2026 | **VERIFIED 2026-08-06** (A1, report trial_2001_date_range_verdict_20260806.md): Knowledge Dump "2005-2018 12.99y" metadata was accurate at run time, BUT trial 2001 consumed Stooq-era CSV (~24k rows, synthetic pre-2005 backfill — commit 3bf6b2e7, later removed by d03a354e). CSV today = 5,936 rows 2005→2026-07-29 clean. days=11061 = len(equity_curve) from Stooq data. Verdict REJECT computed on contaminated data → **NEEDS_RERUN_ON_CLEAN_DATA** before treating as final (confirms #9 for trial 2001) | Underpins the "directional prediction closed" decision — verdict data-basis now known-contaminated; clean re-run needed (5,936-row 2005→2026 CSV available) |
| 2 | Trial #4002 collision (main `trial_ledger.json` vs `hypothesis_registry_d.json`, same ID, different Direction) | **CLOSED + HARDENED 2026-08-06** (B2): confirmed CLOSED no-action (incident 08-05, record never committed, checker 65/0). Added per-direction range ownership check to check_trial_uniqueness.py (8b9c6e20) which immediately caught #4004 FUND-CARRY in MAIN registry (bug-class recurrence) + legacy 1-1000 batch — both fixed (6d7562f3: #4004 moved to registry_d, batch documented). Root cause now closed for this class | Previously: 2nd collision of this class (after #3001/#3004) — root cause now addressed by range-ownership enforcement in the uniqueness ratchet (pre-commit) |
| 3 | Direction D anomaly — main ledger cap raised 1022→1042 directly instead of opening `trial_ledger_d.json`, breaking the project's own Path-B precedent | **RESOLVED 2026-08-06** (B3, commit 7b9990e4): root cause was main ledger `next_available_trial_number=3009` wrongly copied from Direction B (all 3000-block trials live in B's files) — corrected to 1034 (after trial 1033). Cap aligned to 1042 + lock_doc → 07_30 (per superseding stopping_rule_2026_07_30.md L51). auto_increment_trial.py --dry-run now returns 1034 (was STOPPING RULE TRIGGERED on every call). All directions incl Direction H unblocked | Previously blocked auto_increment_trial.py for ALL directions (next 3009 > cap); now resolved — numbering-vs-count scale mismatch fixed for Main |
| 4 | Direction G Step 1 — 7-10 day BTCUSD/EURUSD spread sampling, must cover NFP 2026-08-07 | **STOPPED 2026-08-06 §4.4** — 3 REJECTs (8001/8002/8003); sampler never ran (no lock creator); NFP 08-07 MOOT | EURUSD H4 pre-registration requires new stopping-rule doc (Direction H) + user decision — NOT waiting on sampling |
| 5 | `tradeable_universe.json` self-contradiction — EURUSD/GBPUSD listed in both `measuring` and `excluded` | **RESOLVED 2026-08-06** (cd0f4983) — EURUSD/BTCUSD measuring, GBPUSD/US30 excluded w/ evidence; universe_truth_up_20260806.md | Blocks EURUSD H4 break-even calc; also affects any future work touching this file |
| 6 | Knowledge Dump §6 still says "MEGA_PLAN v3 draft ไม่เคยมีอยู่จริง — อย่าไปหา" | **SOURCE FIXED 2026-08-06** — agentmemory correction mem_mshcep5q_f0ce60d2fea0 + MEGA_PLAN_v2 corrected (b68da984); plan.md not on disk | Any future session loading this memory will repeat the same wrong conclusion until the source doc is corrected |
| 14 | **`scan_for_data_leaks()` — RECLASSIFIED 2026-08-06 (3-level distinction)** — (1) **class-state vector: CLOSED** via `_reset_strategy_class_state` (commit 2820df99); (2) **detection channel: DEAD API** — `check_data_access` (index-based, since 622e8104) never wired into engine.py in any commit; **FORMAL-ACCEPT** (commit e518d095, tautology at wire point); (3) **external-state vector: handled** by C0.3 scanner (commit cec6c91c). 7-channel archaeology (2026-08-06): `git log --all -S` empty (never committed on ANY branch); absent from 19 stashes, 18 worktree working trees, 366 lost-found blobs, 3 dangling commits; reachability audit 2026-07-30 mentions it 0 times; fsck 12,852 unreachable blobs scanned 0 hits → **H1 (hallucination) SUPPORTED, H2 residual = untracked-never-added only**. Current engine = `guard.initialize()` + per-bar `get_slice()` only. Two cautions preserved: (a) consistent with the confirmed hallucinated-deliverable pattern (FOMC event-study, synthetic shocks, Monte Carlo parallel, factor-control — all with fabricated test counts like "18/18 pass" / "21/21 pass" and zero artifacts; doc-18's "290-test zero-regression" matches that shape) — NOT confirmed as pure git-history loss; (b) **do NOT conflate with `5d4a8a2d`** (get_slice end_index clamp + strict raise — that fix is REAL, verified by TestLookaheadGuardChaos, but it only protects the slice API vector, NOT the out-of-band `_full_data` reference vector). Action: re-implement the attr-scan (or formally accept the gap — detection channel already FORMAL-ACCEPTed), plus transcript-integrity investigation of doc-18 | Until resolved, engine-level lookahead protection is incomplete for the out-of-band vector |
| 45 | **Gap-period GO-family verdict audit** — while the #14 gap was open, any GO/APPROVED/PASS verdict is suspect (accidental cheating via future-shaped data is possible; REJECTs remain trustworthy — a strategy that COULD cheat and still REJECTED did not flip to GO). Audit result 2026-08-06 (all registries/ledgers): **#4001 PASS_FEASIBILITY** (funding-arb historical carry) and **#4002 PAPER_TRADING_STARTED** (funding-arb live paper phase — started ON the #4001 feasibility pass) both ran under the gap → flag BOTH as "verdict reliability additionally compromised (ran while lookahead gap open)" on top of their existing issues (#4001 → later FAIL_RIGOR; #4002 paper trading pending fresh authorization per #32). #1031 EXECUTED_EXPLORATORY is exploratory-only (no edge claim) — note, not flag. All REJECT verdicts (1028-1035+, cointegration, etc.) remain trustworthy per the logic above | Prevents a stale GO-family verdict from being cited as evidence of real edge |

---

## 🟠 TIER 1 — High priority, not immediately blocking but load-bearing

| # | Item | Status |
|---|---|---|
| 7 | Cost model 100x FX error / slippage≡spread — **direction of error** (over- vs under-stated) never actually determined | **CLOSED 2026-08-06** (tier1_789_close_20260806.md): bug did not exist / already fixed — MEGA_PLAN_v3_ERRATA Erratum 1 closed both (hallucinated file path backtest/slippage_model.py has zero git history; hand-verified reference EURUSD $20.00 correct). Verified today: execution/cost_model.py L40 slippage separate param + L49 30% of spread; engine.py L726 = get_overfitting_report not 0.01*spread. deep_audit_v3 references were stale |
| 8 | FOREX_EDGE_INVESTIGATION.md (6 trials: GBPUSD/USDJPY REJECT, 4 INCONCLUSIVE) — loader/runner script still **UNKNOWN** | **CLOSED 2026-08-06** (tier1_789_close_20260806.md): runner FOUND = scripts/run_multi_instrument_wf.py (imports validation/walk_forward.py run_walk_forward); artifact FOUND = artifacts/wf_13_instruments/wf_batch_H1_20260712_190128.json (2026-07-12, matches doc date) + multi_instrument_oos.json. Loader CSV/parquet |
| 9 | Provenance backfill contamination re-check across the ~1050 historical trial history (NAS100 68% fake, EURUSD 56% fake pre-2005) | **CLOSED for FOREX_EDGE 6 trials 2026-08-06** (tier1_789_close_20260806.md): runner load_data() uses CSV/parquet with drop_duplicates, never the buggy warehouse path → dedup contamination does NOT apply to these 6. Broader ~1050-trial sweep remains open. OPEN NOTE: wf_batch artifact records total_cost=0.0 — $7/rt commission narrative in FOREX_EDGE.md is not directly from this artifact (Direction H 9001 already re-ran at corrected costs: REJECTED_MIXED) |
| 10 | N-value for multiple-testing correction — claimed fixed (`get_reconciled_n_trials()` single source, N=1050) | Substantially resolved but do one final `grep -rn "N_TRIALS\|n_trials = "` sweep to confirm no other hardcoded value (1508, 1033, 1021) survives anywhere uncalled-out |
| 11 | Sizing bug (100x units→lots) — mt5.py fixed; `risk/engine.py::_layer4()` and `position_sizer_v2.py` wiring/single-source-of-truth status | Needs final confirmation all 3 points compute from one shared conversion point |
| 12 | 5 other MT5 adapter methods with the same unguarded `_ensure_connected()` pattern as the fixed `submit_order()` (cancel_order, get_positions, close_position, get_account_info, set_stop_loss) | Explicitly not patched — each needs its own return-type-appropriate fix |
| 13 | No shared trial-execution harness — bespoke scripts bypass engine/provenance. **CORRECTED 2026-08-06:** split per evidence — (a) **cost-calibration bypass: RESOLVED for TF probe** (`require_cost_calibrated(mode="paper")` added, commit `03a86dc7`); (b) **engine bypass: TF probe is NOT a bypass** — it calls `BacktestEngine.run()` with the same optimizations as the frozen runner; genuine loader bypasses are `validate_dtsmom_strategy.py` etc. (see `check_bypass_loaders.py` baseline); (c) engine-level protection: class-state CLOSED (2820df99), detection FORMAL-ACCEPT (e518d095), external-state scanner cec6c91c — #14 reclassified accordingly | Structural gap, disclosed honestly, not yet addressed with a systematic lint/CI inventory check |
| 15 | EURUSD H4 (TF probe) — n_trades=34 barely clears the 30 minimum; net PF 1.79 computed on stale 7.18bps cost (real cost already 14.17bps, 2x) | **REJECTED 2026-08-06** (9003 DIRH-EURUSD-H4-ASIS, commit 6bce9f59): break-even re-run at real cost (spread 0.1bps + comm 7.0/lot + slippage 0 honest) → be_mult=1.0 < 1.2 selection margin → NOT_SELECTED. Net PF 1.38 post-cost (edge exists but fails margin guard). NOTE: old "14.17bps" was 8-29x commission-unit overstatement (audit_trial_9001_9002_cost_model.md); real RT = 0.78bps |

---

## 🟡 TIER 2 — Governance / process hygiene

| # | Item | Status |
|---|---|---|
| 16 | 4-6 overlapping "master plan" documents (MEGA_PLAN v2, "Full Remediation & Wiring Plan" Phase 1-6, QUANT_OS_MASTER_REMEDIATION_PLAN_v6, 11-prompt audit track, Meta/graxia_mega_plan_v3.md) | Never fully consolidated into one canonical doc despite repeated recommendation (Task 0-Pre.4/F13/F19/F25). **NOTE (2026-08-06):** this checklist is now the master TRACKER (see header relationship note); the others keep their specific-scope roles |
| 17 | Single-writer enforcement — sentinel-lock mechanism built for Direction G Step 1 specifically (atomic create, expiry) | Should become a **general, permanent** mechanism for the whole repo, not a one-off per-task lock |
| 18 | `validation_stack` false-pass design decision (FAIL vs new UNKNOWN/ERRORED status for errored workstreams in gates.py) | Needs user/architectural input — explicitly not patched |
| 19 | Trial-ledger ID collisions beyond the 2 already found — no systematic scan has been run across ALL ledgers (main, _b, _c, _d, _e, _g) at once | Each collision so far was found individually/by accident |
| 20 | 18 stale git worktrees (`C:/tmp/quant_os_*`) — proven to cause at least one real wrong conclusion (v3-file) | 18 worktrees (13+ corrected 2026-08-06); cleanup still pending |
| 21 | 7 git stashes (@0-@12, actual count 7) — @3/@4 share identical message (needs diff before cleanup), @9 possibly TRADING_MODE-related | 7 git stashes (13 corrected 2026-08-06; @3/@4 identical-message + @9 TRADING_MODE checks still pending) |
| 22 | Post-commit hook (Obsidian vault sync) — **status PARTIAL (2026-08-06):** fixed externally 13:26 2026-08-05; syntax valid (`bash -n` passes); behavioral evidence: 1 full sync completed 13:38 post-fix (`[SYNC] Done` + `Vault sync complete.`), but 5 entries "Starting vault sync..." 13:46-13:53 with NO completion lines → sync reliability needs follow-up verification (hanging/interrupted?) | Not fully verified — do not mark done |
| 46 | **doc-18 full claim re-audit** — doc-18 (the session claiming `scan_for_data_leaks` implementation) made other claims; its transcript/artifacts are NOT on disk (2026-08-06 check). Given the confirmed hallucinated-deliverable pattern (see #14 caution a), re-audit EVERY doc-18 claim with the 7-channel git-archaeology methodology (`git log --all -S` per claim + stash/worktree/lost-found/dangling) before trusting any of them | **COMPLETE 2026-08-06** (doc18_reaudit_20260806.md, extended claim coverage): ALL doc-18 claims re-audited 7-channel — scan_for_data_leaks (H1 NOT FOUND), 290-test (NOT VERIFIED), TestLookaheadGuardChaos (MISATTRIBUTED), FOMC event-study (docs only), synthetic_shock (exists, other session), MC parallel (docs only), factor-control (real infra). H1 dominant, H2 residual = untracked-never-added only |

---

## 🟢 TIER 3 — P0 safety blockers, final status check needed

| # | Item | Best known status |
|---|---|---|
| 23 | P0-B1 SL/TP bar midpoint (execution/fill_model.py) | Unclear in most recent docs — re-verify |
| 24 | P0-B2 swap cost — wired in backtest, **confirmed repeatedly still missing from live path** | Still open (reconfirmed multiple sessions) |
| 25 | P0-B3 kill switch corrupt JSON fail-closed | Believed fixed early — re-verify with current code |
| 26 | P0-B4 CORS wildcard | Unclear latest status |
| 27 | P0-B9 AlertManager (was dropping all alerts) | ✅ Fixed — rewrote to log + real Telegram delivery |
| 28 | P0-B10 pre-trade gate wiring (RiskEngine construction TypeError in webhook.py) | ✅ Fixed and verified |
| 29 | P0-B11 crash recovery (`realtime_reconciler.reconcile_now()`) | ✅ Wired into FastAPI lifespan startup |
| 30 | P0-B12 auto_retrain dummy metrics | ✅ Fixed — real sklearn-based evaluation |
| 31 | Kill-switch's own second, independent Telegram notification bug (wrong module/method, silently swallowed) | ✅ Fixed |

---

## 🔵 TIER 4 — Research direction

| # | Item | Status |
|---|---|---|
| 32 | Funding-arb (Direction D) | **FAIL_RIGOR** — final verdict after rigorous re-test. Automation of paper-trading harness (Scheduled Task) explicitly blocked pending fresh, specific user authorization. **ADDITIONAL FLAG (2026-08-06):** #4001 PASS_FEASIBILITY + #4002 PAPER_TRADING_STARTED ran while the #14 lookahead gap was open — verdict reliability additionally compromised |
| 33 | Basis/carry crypto research | Named in redirect plan, **never started** |
| 34 | Cointegration pairs (Direction E, #5001 BTC/ETH, #5002 Gold/GDX) | REJECTED, closed properly (MacKinnon-adjusted p-values, methodology documented) |
| 35 | Direction G (TF-matching, BTCUSD/EURUSD Donchian/Session) | **STOPPED 2026-08-06 §4.4** (8001/8002/8003 REJECT); sampler never ran; see #4. Direction H (new stopping-rule doc) required for EURUSD H4 — decision in Sub-project B |
| 36 | "Keep originating new hypotheses" (vs. replicate-published-strategy) | User's explicit choice — given 100%-reject track record across every mechanism tried so far, worth periodically revisiting whether this remains the right call |
| 37 | ML/AI components (auto_retrain, DriftMonitor, autonomous/decision_engine) | User explicitly deferred all three — correct to leave alone until a specific need arises. **NOTE (2026-08-06):** ML models are the highest-risk accidental exploiters of the #14 out-of-band vector — if ever re-opened, the attr-scan must exist first |

---

## ⚪ TIER 5 — Testing/CI/lower priority

| # | Item | Status |
|---|---|---|
| 38 | Release gate — GREEN, but 27 real logic failures (QOS-RB-*) sit in quarantine, never counted in pass/fail | Needs eventual fixing, not urgent |
| 39 | 117 tests missing from release-gate baseline (3639 claimed vs 3522 actual) | Re-baselined but root cause of the gap never explained |
| 40 | 60 env-gated skips — 8 documented reasons | Should be spot-verified as legitimate, not just counted |
| 41 | mypy gate blocked by 36 errors across 12 files from 23 uncommitted polluted files (other sessions) | Blocks committing verified fixes — needs tree cleanup (not your call to force) |
| 42 | docker-compose smoke test of aiohttp/pydantic-settings version bump | Never actually run in a live deployment |
| 43 | `RolloverFilter`, `RiskBudget`, `update_trailing_stop()`/`_setup_post_fill_stop_loss()`, `AntiMartingaleSizer` | All deferred/dead code with zero live callers — fine to leave until a strategy actually needs them |
| 44 | News/sentiment intelligence sub-project — ticker extraction rate never measured on full corpus (only anecdotal examples); sentiment/impact score **never backtested against real price moves** | This is the single most important missing step if this system is ever meant to feed quant_os as alt-data |

---

## Suggested order of attack (updated 2026-08-06)

0. **Tier 0 sweep Sub-project C DONE** (C0-C4 commits: a30a8b4d e518d095 cec6c91c 8a1b046b cd0f4983 b45c2ece b68da984 97cd0a1c 41ae6e4f 7295c6fc b1498609 + agentmemory corrections) — #2/#5/#6/#14/#46 statuses refreshed; next: Sub-project B decisions (#2 confirm, #3 revert-vs-separate, Direction H open?)
1. **Tier 0 #1 and #6 first** — both are "is our foundational conclusion actually correct" questions with cheap verification (open a JSON, edit one doc section). #6 is now CORRECTED in this file — fix the source doc (Knowledge Dump §6) too.
2. **Tier 0 #14** — the newly-upgraded P0 GAP: decide re-implement attr-scan vs formally accept; run the doc-18 transcript-integrity investigation (#46) in parallel — this is now the biggest safety item in the list.
3. **Tier 0 #2/#3** — put a firm decision in front of the user; these keep recurring because they're stuck in limbo, not because they're hard.
4. **Let Direction G Step 1 (#4) run its course** — it's calendar-bound, nothing to do but wait and monitor the sentinel lock.
5. **Tier 1 #7-#9** — the three biggest remaining "is our historical REJECT evidence actually trustworthy" questions. These have been assigned multiple times across sessions without confirmed completion — prioritize closing them for real this time.
6. Everything else in Tier 1-3 can proceed opportunistically/in parallel — none of it blocks the others.
7. Tier 4/5 items are either correctly deferred by explicit user choice or genuinely low-urgency — revisit periodically, don't let them create false urgency.

---

## Tier 0 sweep execution log (2026-08-06)
| Task | Commit | Outcome |
|---|---|---|
| C0.1 guard verify | a30a8b4d | 3 protection levels confirmed |
| C0.2 check_data_access | e518d095 | FORMAL-ACCEPT (tautology at wire point) |
| C0.3 external-state scan | cec6c91c | TF probe CLEAN; scanner tests 3/3 |
| C0.4 doc-18 re-audit | 8a1b046b | H1 supported, H2 residual |
| C1.1 universe fix | cd0f4983 | EURUSD/BTCUSD measuring; GBPUSD/US30 excluded |
| C1.2 evidence report | b45c2ece | universe_truth_up_20260806.md |
| C2.1 MEGA_PLAN_v2 | b68da984 | v3-supersedes claim corrected |
| C2.2 agentmemory | (MCP) | correction mem_mshcep5q_f0ce60d2fea0 |
| C2.3 supersession refs | 97cd0a1c | master-tracker refs added |
| C3.1 Khubiev fail-closed | 41ae6e4f | 13/13 tests |
| C3.2 trial 1028 footnote | 7295c6fc | same-bar-fill note |
| C3.3 mlmr + manifest | b1498609 | explicit fallback + degenerate flag |
