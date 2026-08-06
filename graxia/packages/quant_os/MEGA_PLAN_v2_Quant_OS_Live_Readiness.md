# MEGA PLAN v2 — Quant OS Live Trading Readiness (Enhanced)

**Date:** 2026-07-20 | **Version:** 2.0 | **Status:** `NO_GO` → `PASS_TO_NEXT_PHASE` (pending v2 gate additions)
**Supersedes:** MEGA PLAN v1.0 (2026-07-20)
**Evidence Base:** 35+ audit documents, 6 parallel deep-dives, 3 trial ledgers
**Constitution:** INV-001 through INV-013 enforced throughout
**Change basis:** Critical methodology review — 26 findings (7 CRITICAL, 6 HIGH, 9 MEDIUM, 2 LOW), expanded after a third independent audit session and a fourth remediation session (2026-07-22 to 2026-07-28) surfaced additional evidence-integrity and process-control risks

---

## ⚠️ 2026-07-28 provenance note (read first)

This file previously existed on disk only as a **171-line condensed summary** (F1-F12 only, dated 2026-07-20) while the actual working document — with F13 through F27, all eight Task 0-Pre sub-tasks, and every appendix — existed only in conversation/session context and was never saved back here. That is the exact single-source-of-truth failure this document itself warns about in F13/F19/F25. This write reconciles the two: the full F1-F27 content below is now the canonical, on-disk version. The prior condensed file is preserved at `MEGA_PLAN_v2_Quant_OS_Live_Readiness.CONDENSED_20260720.md.bak` for reference, not deleted.

**Also resolved same day:** a "MEGA_PLAN v3 draft (2026-07-22)" is referenced by two orphaned errata files (`MEGA_PLAN_v3_ERRATA_20260722.md`, `MEGA_PLAN_v3_ERRATA_CORRECTION_20260725.md`) but **no v3 base document exists anywhere in this repository** — grepped, not found. Their substantive content (annualization-factor audit, cost-model-direction audit) is already incorporated here as F15/F16. Treat v3 as an abandoned/never-finalized draft; this v2 document remains canonical. `Meta/graxia_mega_plan_v3.md` **IS this plan's successor** — its own header (L4) reads "Supersedes v2.0" (locked 2026-06-26, RESEARCH-VERIFIED EDITION). Prior "unrelated document" claims (2026-07-28) were wrong; see agentmemory mem_mscvvnav_07be3d8c185d (2026-08-03 correction). **CORRECTED 2026-08-06** per Tier 0 sweep C2 (spec §2.7).

**Trial #2001 status update (2026-07-28):** Task 0A.1-0A.2 have already been executed (2026-07-20, before this note was added) — see `reports/edge_search_cross_sectional_20260720.json`. Result: `dk_t = -2.1255`, `label_shuffle_p = 0.0`, verdict **REJECT**. NAS100 (-99.9997%) and US30 (-95.55%) legs sanity-checked against raw price data 2026-07-28 (no split/discontinuity artifact found, max single-day move 12.6%) and confirmed to use direct portfolio-weight returns, not the lot-sizing path affected by the F27 contract-spec bug — this REJECT verdict is not believed to be contaminated by that bug. Per this document's own stopping-rule framing (see bottom), a REJECT here is grounds to close the directional-prediction research line, pending the user's explicit sign-off.

**Shadow Mode status update (2026-07-29):** Implemented and committed. `SHADOW_MODE=true` (in `.env`) connects MT5 read-only for live market data while executing against `PaperAdapter` — no real orders are ever submitted (MT5 read-only guards + `ShadowAdapter` routing). Commits: `557e783e` (shadow flag), `fdb36741` (INV-014), `a29c7564` (ShadowAdapter routing + XAUUSD contract-size fix). This is the safe "demo-account read-only + paper execution" path; it does NOT need a `DEMO` `TradingMode` enum value.

---

## 🔍 CHANGELOG — v1 → v2 (Critical Review Findings)

| # | Sev | Finding | v1 Gap | v2 Fix |
|---|-----|---------|--------|--------|
| F1 | HIGH | Trial count discrepancy | Header says "29 trials" (Direction A); table sums to ~35-37 individual instances (batch of 13 counted as 1 row) | Task 0-Pre: reconcile against `trial_ledger.json` before any new work |
| F2 | **CRITICAL** | No multiple-testing correction across trial history | Trial #2001 is the 34th hypothesis tested but uses a raw, unadjusted threshold (dk_t>2.0, p<0.05) as if it were the first | Deflated Sharpe Ratio (N=34, variance of prior Sharpes) added as hard Phase 0A gate criterion |
| F3 | **CRITICAL** | Cost model sequencing mismatch | Phase 0A uses generic cost model; real spread (0B) and swap costs (P0-B2, fixed in Phase 1) arrive AFTER the GO decision | Cost-sensitivity stress test (1x/1.5x/2x) added as Phase 0A gate; edge must survive 1.5x assumed cost |
| F4 | HIGH | No edge re-validation after P0 fixes | P0-B1/B2/B12 change backtest fidelity but Phase 0A result isn't re-checked before Phase 2 | Task 1.14 added: re-run edge search with fixed engine; must still pass before Phase 2 |
| F5 | MEDIUM | N=7 mislabeled as "cross-sectional momentum" | Cited literature (Jegadeesh-Titman) uses 100s-1000s of names; N=7 has far less statistical power than implied | Relabeled as multi-asset TSMOM w/ ranking overlay; jackknife robustness check added |
| F6 | MEDIUM | PBO/Deflated Sharpe in wrong phase | Listed as Phase 2 (paper trading) criteria, but properly computed via CSCV on the Phase 0A backtest | Moved to Phase 0A/Decision Gate; Phase 2 keeps live version as confirmatory only |
| F7 | MEDIUM | `mt5_csv` data source ambiguous | Could mean historical replay, not live feed — would make Phase 2 a disguised backtest | Explicit live-feed requirement + forward-only date invariant added |
| F8 | LOW | P0-B13 marked "Live Block? NO" but classed as P0 | Inconsistent severity labeling | Reclassified to P1 (architecture debt), decoupled from hard gate |
| F9 | MEDIUM | No holdout FAIL branch | Decision Gate #9 requires "holdout validated" but no policy on what happens if it fails | Explicit PASS/FAIL decision table added |
| F10 | LOW | Stopping rule doesn't cite which 4 trials triggered it | Weakens INV-012 auditability | Explicit trial ID citation required in Task 0-Pre |
| F11 | MEDIUM | INCONCLUSIVE forex trials not folded into stopping-rule tally | Ambiguous whether 4 INCONCLUSIVE results count as failures | Explicit handling policy added |
| F12 | MEDIUM | No explicit regime-coverage requirement for backtest period | Data range/years not stated | Explicit data range + regime-span requirement added to Phase 0A |
| F13 🆕 | HIGH | Two competing P0/blocker inventories exist (this plan's 13 P0-Bxx items vs. a separate 11-prompt audit session's findings — JWT audience, rate-limiter leak, orchestrator SRP, E2E tests) with no overlap check | Risk of declaring "P0s fixed" using one list while the other list's live-blocking items (e.g. P0-B1 SL/TP midpoint, P0-B2 swap costs, P0-B9 AlertManager) remain untouched | Task 0-Pre.4 added: reconcile both blocker lists into one master inventory before Phase 1 begins |
| F14 🆕 | HIGH | External "deep research" edge document (8 proposed edges) cites sources that were not independently verified before being treated as evidence for a 20-40% return improvement roadmap | Spot-check of 4/8 citations found: 1 real paper with materially misrepresented numbers + wrong asset class (IMCA/Pankwaen), 1 citation that could not be located under the stated title/journal at all (Huang et al. 2026, "Journal of the European Academy Open University"), 2 real and reasonably represented (Khubiev et al.; Chen et al. MARS) | Task 0-Pre.5 added: mandatory citation verification pass, per-edge trust classification, before any of the 8 proposed edges enters the hypothesis backlog |
| F15 🆕 | **CRITICAL** | Annualization bug found in `backtest_suite.py:127` (`sqrt(252*96)` instead of `sqrt(252)` — 10x Sharpe inflation for daily data) | Confirmed fixed for the Phase 9 label-shuffle re-test, but **unverified whether `momentum_factor_rotation.py` / `edge_search_cross_sectional.py` (the actual Trial #2001 code path) shares this bug**. If it does, Task 0A.1's dk_t could be inflated ~10x, producing a false GO | Task 0-Pre.6 added: verify annualization formula in the exact code path Task 0A.1 will use, BEFORE running Task 0A.1. **UPDATE 2026-07-25 (MEGA_PLAN_v3_ERRATA_CORRECTION_20260725.md):** empirical re-check (timestamp spacing + per-bar vs daily-aggregated Sharpe invariance test) found this erratum's own mechanism and magnitude unsupported — the proposed `sqrt(252)` fix would itself have been a regression. Do not apply the original F15 fix as literally stated; treat as resolved-no-bug pending any further evidence. |
| F16 🆕 | **CRITICAL** | Cost model bugs in `backtest/slippage_model.py` (slippage ≡ spread; 100x error on FX pairs) mislabeled as P2 "performance" issue | If FX cost was overstated ~100x, the already-REJECTED FOREX_EDGE_INVESTIGATION verdicts (GBPUSD t=-8.77, USDJPY t=-8.57, etc.) may be false negatives — a real edge could be hidden under fabricated cost. Direction of the error (over- vs under-stated) is not yet known | Task 0-Pre.6 added: determine error direction; if costs were overstated, flag prior FX REJECTED verdicts as `NEEDS_RETEST`, not final. **UPDATE (MEGA_PLAN_v3_ERRATA_20260722.md, Erratum 1):** closed/strengthened — the file originally cited as evidence for this bug never existed; re-verification found no such cost-model bug in the live code path. |
| F17 🆕 | HIGH (reclassified from P1) | Walk-forward purge/embargo defaults wrong (`backtest/walk_forward.py:125-126`), documented as "lookahead bias risk" but only P1-severity | Lookahead bias in the walk-forward/CSCV harness directly threatens the validity of Task 0A.5 (PBO computation) — the tool meant to *detect* overfitting may itself leak information between folds | Task 0-Pre.6 added: fix + independently re-verify purge/embargo logic before any PBO result from Task 0A.5 is trusted |
| F18 🆕 | MEDIUM | `governance/validation_stack.py` described as "broken, blocks paper trading" with no clarification of what it validates | Unclear whether this is the same machinery Task 0A.5 depends on for PBO/DSR, or a separate governance layer | Task 0-Pre.6 added: clarify scope and dependency before Phase 0A |
| F19 🆕 | MEDIUM | A third, independent audit session produced yet another overlapping defect inventory (P0-1..17, P0-API-1..4, P0-STAT-1..2, P1-A..E) not yet reconciled with either the MEGA_PLAN P0-Bxx list or the earlier 11-prompt session's T001-T023 list | Four parallel, partially-overlapping tracking schemes now exist for the same codebase across different sessions, with no single source of truth — "fixed" status can't be fully trusted until everything is in one place | Task 0-Pre.4 scope expanded to explicitly absorb this third track as well |
| F20 🆕 | MEDIUM | A label-shuffle test on simple single-asset momentum (7 symbols, `price > MA(12)`) was run and is at risk of being conflated with fulfilling Task 0A.1 (Trial #2001) | The tested strategy is single-asset absolute momentum (same family as already-REJECTED Mom126/Mom252), **not** the pre-registered multi-asset ranking momentum (`momentum_factor_rotation.py`, top_n=2, vol-targeted, 5-bar rebalance) that Trial #2001 specifies. Also appears to have been run without a prior entry in `hypothesis_registry.json` | Explicit note added: this result is supporting evidence (same underlying signal family), not a substitute for running Task 0A.1. Going forward, no test may run before its pre-registration entry exists, regardless of which session/agent runs it |
| F21 🆕 | **CRITICAL** — ✅ **GUARD BUILT & VERIFIED 2026-07-28** | A "150+ tools" research report recommends registering `hybrid_mom_mr.py` (and possibly `liquidity_sweep_v2.py`) into the live alpha engine this week as a "$0 cost quick win" | `hybrid_mom_mr.py` corresponds to HMR20/HMR60 — **already REJECTED** (dk_t -0.41/-0.42, label-shuffle p=0.295 NO_EDGE). At least 10 of the 25 "unused strategies" the report lists map onto already-REJECTED trials but are NOT flagged as such in the report | **RESOLVED**: `scripts/check_strategy_against_ledger.py` built, ran against all 43 non-infra `strategies/*.py` files. Results: `hybrid_mom_mr.py` → BLOCKED (confirmed match to HMR20/60). `liquidity_sweep_v2.py` → CAUTION (shares mechanism with REJECTED v1 but has genuine new filters — needs its own trial number, not silent registration, not a blanket clear). `mlmr.py` → CLEAR (verified distinct from `mrb.py`, never tested). Full breakdown as of 2026-07-28: 24 BLOCKED, 8 CLEAR, 4 CAUTION, 7 INFRA, 0 UNGATED_POSITIVE (the 2 that existed under F27 were resolved and reclassified BLOCKED same day — see F27 update below). Also fixed: several strategy docstrings cited stale trial IDs (e.g. `cot_positioning.py` said #1009, real ledger entry is #2007) — corrected in the guard script's citations. |
| F22 🆕 | **CRITICAL** — ✅ **BUG REPRODUCED & FIXED 2026-07-28** | `validation/deflated_sharpe.py`'s `deflated_sharpe` output field was found, in a separate remediation session, to literally equal `probability_alpha` (a p-value) rather than a Sharpe-space quantity — caught and worked around in one call site (`hot_swap()`), but not confirmed fixed at the source, and its relationship to the Task 0A.5 code path (`scripts/compute_deflated_sharpe.py`) is unknown | If Task 0A.5 uses (or duplicates) this same buggy field semantics, a GO decision on Trial #2001 could be based on a p-value being misread as a Sharpe estimate | **RESOLVED (different, related bug)**: `compute_deflated_sharpe.py::load_trial_count()` was found to look for keys `reconciled_trial_count`/`total_trials`/`n_trials` — none of which exist in what `reconcile_trial_ledger.py` actually produces (`total_n_for_multiple_testing`). Reproduced the resulting `KeyError` live, fixed by widening accepted key aliases, re-ran and confirmed it now reads N correctly. This fixes the *N-loading* path; the separately-reported *field-semantics* bug (`deflated_sharpe` = `probability_alpha`) was not independently re-verified in this script's own Sharpe-side computation — flag if this script's DSR output is ever load-bearing for a GO decision. |
| F23 🆕 | **CRITICAL** — ✅ **RESOLVED (universe amended)** | NAS100 — part of Trial #2001's pre-registered 7-asset universe — was found to have zero real cost-calibration data (`status: "UNVERIFIED_NO_DATA"`) and was removed from `tradeable_universe.json` entirely in a separate remediation session (2026-07-26) | Task 0A.1 could not run as originally specified with a 7-asset universe including NAS100 without real cost data | `config/tradeable_universe.json` (v1.1.0, 2026-07-26) formally excludes NAS100 with a documented reason (see file's own `_meta.data_integrity_fix_20260726` field). **Note**: Task 0A.1 was actually run 2026-07-20 (before this exclusion) still using the 7-asset universe including NAS100 — this was a genuine backtest-mechanics result (verified 2026-07-28, no data artifact), not a live-tradeable-universe question, so the REJECT verdict stands regardless of NAS100's later cost-data exclusion. Going forward, any *new* trial in this universe should use the amended 6-asset universe (`XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, US30`) per `tradeable_universe.json`. |
| F24 🆕 | HIGH — ✅ **AUDITED 2026-07-28, mostly resolved** | Warehouse OHLCV data source found to be 6x-duplicated (300,000 rows → 50,000 unique) in a separate remediation session, fixed via `_dedupe_warehouse_ohlcv()` going forward | Duplicated (non-independent) observations inflate apparent sample size in any t-test/DK-test, making p-values look artificially more significant than they are, in either direction. Unknown whether any of the 33+ historical REJECTED trials used the undeduplicated warehouse path | **RESOLVED for Direction A (1000-1021), Direction B (2001-2011), the pooled 17-strategy DK-test, and the 2B.5b retrain** — all confirmed via actual runner script inspection (not just trial IDs) to load via CSV/parquet/DuckDB, never the buggy warehouse path. Best evidence: `scripts/auto_retrain.py:65-73` has a comment showing the bug was found and deliberately routed around (`source="duckdb"`) *before* the 2B.5b retrain ran — that NO-GO (DSR -0.78) result was never at risk. **Still open**: the 6 FOREX_EDGE_INVESTIGATION.md trials (2 REJECT, 4 INCONCLUSIVE) — actual runner script/loader could not be located. Do not cite these 6 as "clean" (for dedup OR for the F16 cost-model-direction question) until the runner is found. Full audit: `reports/warehouse_dedup_exposure_audit_20260728.md`. |
| F25 🆕 | HIGH — ⚠️ **PARTIALLY RESOLVED 2026-07-28** | A fourth, independent "master plan" was discovered — a separate "Full Remediation & Wiring Plan" with its own Phase 1-6, Phase 2A/2B/2C sub-phases, and Wave 8/9 gates tracked in `CHANGE_CONTROL.md` — running in parallel to MEGA_PLAN v2, the 11-prompt audit track, and the third deep-audit session, with no declared supersession relationship between any of them | Four (in fact, closer to six, once `LIVE_TRADING_READINESS_MASTER.md` and the orphaned "v3 draft" errata are counted) overlapping roadmap/gate structures now govern the same live-readiness question for the same codebase | **Status as of 2026-07-28**: this document (MEGA_PLAN v2) is confirmed canonical going forward. `CHANGE_CONTROL.md` (pointing to `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md`) was already listed as superseded in this document's own header before this note was added, but `CHANGE_CONTROL.md` itself does not yet carry a reciprocal supersession note — **still needs one, not yet added**. `LIVE_TRADING_READINESS_MASTER.md` (2026-07-12) was never previously in any supersession chain — also still needs a note. The referenced "MEGA_PLAN v3 draft (2026-07-22)" was searched for exhaustively and does not exist as a file anywhere in the repo; treated as abandoned, its two errata files' substance already folded into F15/F16 above. `Meta/graxia_mega_plan_v3.md` supersedes v2.0 per its own header (L4) — prior "unrelated" claim wrong. **CORRECTED 2026-08-06** per Tier 0 sweep C2 (spec §2.7). |
| F26 🆕 | MEDIUM | Multiple autonomous coding sessions were found operating in parallel on the same git working directory, causing git-index collisions and 3+ unauthorized commits that had to be caught via independent `git log` verification and reset | Uncoordinated concurrent agents against a live repo is a process risk that scales with proximity to live trading — a race condition during a risk-engine edit is a materially worse failure mode than one during documentation | Task 0-Pre.7 added: establish a single-writer rule (one active coding session/agent per repo at a time, or an explicit lock file) before further remediation work. **Not yet formally adopted** — still an open recommendation, not an enforced mechanism, as of 2026-07-28. |
| F27 🆕 | **CRITICAL** — ✅ **RESOLVED 2026-07-28 (REJECT, registered)** | Two positive "GO"-verdict result files were found sitting completely outside the trial ledger during the F24 audit: `reports/pooled_donchianp1_results.json` (dk_t=+7.93, 2026-07-19) and `reports/pooled_tsmdxydivergence_results.json` (dk_t=+4.95, 2026-07-19) — for `strategies/donchian_p1.py` and `strategies/tsm_dxy_divergence.py`. Never counted toward N, never Benjamini-Hochberg corrected, never entered in any ledger | Both results were driven almost entirely by EURUSD/GBPUSD legs (profit_factor 23-32) while XAUUSD was flat — matching a documented tick-size/pip-scaling artifact signature, but pattern-matching to a known bug signature is not the same as confirming it | **RESOLVED via direct forensics, not pattern-matching**: commit `59a15bd0` (same day as the original runs, 2026-07-19 14:48:22) fixed a symbol-threading bug that had defaulted ALL non-XAUUSD contract specs to gold-shaped values — confirmed via commit message + `git show` diff + filesystem timestamps showing the original GO runs (05:29/05:31) predated the fix (14:46/14:48). Re-running post-fix collapsed dk_t (7.93→3.68/3.32, 4.95→2.90) but did not zero it out. Per-asset breakdown of the survivor then showed **XAGUSD** as the new outlier (nw_t=5.76-5.88, PF=29-34) — checked source directly: XAGUSD (and NAS100, US30, `BTCUSD`) are still missing from `InlineContractSpec.for_symbol()`'s symbol map, same bug class, still unfixed. Jackknife (leave-one-asset-out, reusing the existing harness's `universe=` param, no engine changes): excluding XAGUSD alone flips pooled dk_t from +3.32 to **-0.14**; excluding BTCUSD barely moves it (confirms BTCUSD isn't the driver). The entire surviving signal was a single-asset contract-spec artifact. Registered as trials **#2009 (REJECTED), #2010 (REJECTED), #2011 (REJECTED)** in `trial_ledger_b.json`/`hypothesis_registry_b.json`. Full forensic chain: `reports/f27_pip_scaling_verification_20260728.md`. Separate, non-blocking hygiene ticket opened: `InlineContractSpec` and `risk/position_sizer.py` have two disagreeing contract-spec tables in the same codebase — not yet reconciled, does not change any verdict. |

---

## 🔴 EXECUTIVE VERDICT — NOT READY

| # | Blocker | Evidence | Severity |
|---|---------|----------|----------|
| 1 | No proven edge — All 33+ trials REJECTED (count pending F1 reconciliation) | `CONSTITUTION.md:98` | CRITICAL |
| 2 | STOPPING RULE triggered — 4 consecutive failures (trial IDs pending F10 citation) | `CONSTITUTION.md:98` | CRITICAL |
| 3 | 13 P0 infrastructure bugs (12 hard live-blockers + 1 reclassified per F8) | `AUDIT_INDEX.md:23-25` | CRITICAL |
| 4 | Cost baseline unreliable (33x disagreement) | `READINESS_VERIFIED.md:49-53` | CRITICAL |
| 5 | Paper trading not started (0/60 days) | `READINESS_VERIFIED.md:112` | CRITICAL |
| 6 🆕 | No multiple-testing correction applied to trial #2001 candidacy | F2 | CRITICAL |
| 7 🆕 | Cost model used in edge discovery not yet reconciled with measured live spread | F3 | HIGH |
| 8 🆕 (2026-07-28) | Trial #2001 has actually already been run and REJECTED (dk_t=-2.13) — see provenance note at top | `reports/edge_search_cross_sectional_20260720.json` | INFORMATIONAL — updates blocker #1's count, does not change verdict |

---

## PLAN STRUCTURE (v2)

```
PHASE 0-PRE (7-9 days) → PHASE 0A (2.5 wks) → PHASE 0B (1 wk, parallel) → DECISION GATE
   Reconciliation       Edge Disc. + stress    Spread Meas.              (13 conditions)
        ↓
PHASE 1 (3.5 wks) → RE-VALIDATION GATE → PHASE 2 (9 wks) → PHASE 3 (2 wks) → LIVE
   Fix P0 Blckrs      Edge still holds?     Paper Trading    Live Gates      Gradual scale
```

**MUST stop at any gate if criteria not met. No sunk-cost fallacy. This applies equally to the Decision Gate, the new Re-Validation Gate, and Phase 3.**

---

## 📊 EVIDENCE BASELINE — Every Trial Ever Run

### 🆕 PHASE 0-PRE: Reconciliation & Verification (7-9 days, BLOCKING — do first)

Before any new hypothesis (Trial #2001) is registered, eight things must be closed: the trial count discrepancy (F1), the stopping-rule citation gap (F10), the INCONCLUSIVE handling policy (F11), the dual-blocker-list conflict (F13/F19), the external-research citation trust level (F14), three evidence-base integrity risks (F15/F16/F17/F18), a strategy re-use blocklist plus five process/data-integrity risks (F21-F26), and two ungated positive results requiring unit-scaling verification plus N-methodology transparency (F27). **Status as of 2026-07-28: F1, F2 (via DSR fix), F21, F24, F27 are resolved; F23 is resolved; F13/F19/F25/F26 are partially resolved (this document reconciled, others still need reciprocal supersession notes; single-writer rule still not formally adopted).** This is a data-integrity prerequisite, not optional cleanup — none of it is new engineering work, it's making sure the plan is arguing from facts that have actually been checked.

**Task 0-Pre.1:** Reconcile Direction A count — ✅ **DONE.** `reports/trial_count_reconciliation_20260720.json` — `total_n_for_multiple_testing: 1050` (conservative), `1033` (strict). Breakdown (`total_n_breakdown`) traces `direction_a_tested: 1020` directly to `research/trial_ledger.json`'s own `cumulative_trial_count: 1021` field — not an invented number, independently verifiable.

**Task 0-Pre.2:** Cite the exact stopping-rule trigger — ✅ **DONE.** `reports/stopping_rule_trigger_citation.json` — documents stopping rule triggered in both Direction A (4 consecutive p>0.05 failures: trials 1003-1006) and Direction B (3 consecutive dk_t<0 failures: trials 3004-3006).

**Task 0-Pre.3:** Resolve INCONCLUSIVE handling policy (F11) — recommended default: treat INCONCLUSIVE as **not yet resolved**, excluded from stopping-rule failure count, but ineligible to be cited as "evidence of edge" either — log as `STATUS: UNDERPOWERED`, revisit only with pre-registered larger sample size.

**Task 0-Pre.4 🆕:** Reconcile the two (really: four) competing P0/blocker inventories (F13/F19) — **still open**. Build one master blocker list with a single ID scheme, tagging each item with origin source, live-block Y/N, fix status, evidence file:line, and which test proves the fix. No blocker may be marked "fixed" project-wide until it exists, with a status, in the single master list.

**Task 0-Pre.5 🆕:** Citation verification pass on the external "deep research" edge document (F14) — spot-check already found 1 unlocatable citation, 1 real-but-misrepresented paper, 2 real-and-reasonable. Policy going forward: any edge whose supporting citation is classified NOT LOCATED or MISREPRESENTED may still be investigated on its own mechanistic merits, but enters the backlog with no pre-assumed expected-impact number.

**Task 0-Pre.6 🆕:** Evidence-base integrity checks (F15, F16, F17, F18) — ✅ **F15 and F16 resolved** (see changelog: F15's proposed fix was itself found to be a regression and was not applied; F16's underlying bug was found not to exist in the live code path). **F17 (purge/embargo independent re-verification) and F18 (governance/validation_stack.py scope clarification) remain open.**

**Task 0-Pre.7 🆕:** Fourth-session findings — strategy re-use blocklist, DSR reconciliation, universe/data blockers, process control (F21-F26) — ✅ **F21, F23, F24 resolved.** F22 partially resolved (N-loading path fixed; field-semantics claim not independently re-verified). F25 partially resolved (this document reconciled; `CHANGE_CONTROL.md` and `LIVE_TRADING_READINESS_MASTER.md` still need reciprocal supersession notes — **action item, not yet done as of this write**). F26 (single-writer rule) still an open recommendation, not enforced.

**Task 0-Pre.8 🆕:** Ungated positive results + N-methodology transparency (F27) — ✅ **RESOLVED.** Both orphan results (`donchian_p1`, `tsm_dxy_divergence`) traced to a real, verified bug (symbol-threading, then a second still-open instance affecting XAGUSD/NAS100/US30/BTCUSD), confirmed via direct jackknife that the surviving signal was a single-asset artifact, registered as REJECTED trials #2009-2011. N-methodology already transparent per Task 0-Pre.1.

**Acceptance:** All eight sub-tasks produce a signed-off artifact before Task 0A.1 begins. As of 2026-07-28, Task 0A.1 has *already run* (2026-07-20, before several of these sub-tasks were completed) — this is a process-order violation worth noting (edge discovery ran before reconciliation was fully done), though the specific trials this session verified (Trial 2001/1022, and F27's 2009-2011) do not appear to have been invalidated by the gaps that existed at the time. `CHANGE_CONTROL.md` entry required for full formal closure.

---

### Direction A — Single-Asset Technical (count pending 0-Pre reconciliation; ALL REJECTED or UNTESTABLE)

| Trial | Strategy | Metric | Instrument | Verdict | Source |
|-------|----------|--------|------------|---------|--------|
| 1001 | RYDC Arm A | p=0.968 | XAUUSD | REJECTED | CONSTITUTION.md:92 |
| 1003 | Cross-Asset Momentum | p=0.598 | XAUUSD | REJECTED | CONSTITUTION.md:93 |
| 1004 | Session Pattern | p=0.934 | XAUUSD | REJECTED | CONSTITUTION.md:94 |
| 1005 | Macro Regime MR | p=0.244 | XAUUSD | REJECTED | CONSTITUTION.md:95 |
| 1006 | Gold-Silver Spread | p=0.505 | XAUUSD/XAGUSD | REJECTED | CONSTITUTION.md:96 |
| 1007 | BTC Vol Clustering | p=0.248 | BTCUSD | REJECTED | READINESS_VERIFIED.md:29 |
| 1008 | Cross Asset Vol Rank | p=0.610 | BTCUSD | REJECTED | READINESS_VERIFIED.md:30 |
| 1009-1021 | gold_ict_batch (13 sub-trials) | dk_t=0.52 | XAUUSD | REJECTED | trial_ledger.json |
| 1022 | Multi-Asset TSMOM w/ Ranking (Trial "#2001" per this plan's own numbering) | dk_t=-2.1255 | XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 (pooled) | **REJECTED (2026-07-20)** | reports/edge_search_cross_sectional_20260720.json |
| RSI_20_80 | RSI 20/80 | dk_t=-0.22 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:33 |
| RSI_30_70 | RSI 30/70 | dk_t=-0.36 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:34 |
| RSI_25_75 | RSI 25/75 | dk_t=-0.82 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:47 |
| Mom252 | Momentum12M_252 | dk_t=-0.39 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:35 |
| Mom126 | Momentum12M_126 | dk_t=-0.52 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:40 |
| HMR20 | HybridMomMR_20 | dk_t=-0.41 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:36 |
| HMR60 | HybridMomMR_60 | dk_t=-0.42 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:37 |
| DC10 | Donchian_10 | dk_t=-0.61 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:44 |
| DC20 | Donchian_20 | dk_t=-0.75 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:45 |
| DC55 | Donchian_55 | dk_t=-0.59 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:42 |
| DCAX | DonchianADX_10_25 | dk_t=-0.53 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:41 |
| BSQZ | BollingerSqueeze | dk_t=-0.60 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:43 |
| LS | LiquiditySweep | dk_t=-0.52 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:39 |
| VB15 | VolumeBreakout_1.5 | dk_t=-0.77 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:46 |
| VB20 | VolumeBreakout_2.0 | dk_t=-0.49 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:38 |
| MRB | MeanReversionBollinger | NO SIGNALS | — | **UNTESTABLE** (not REJECTED — see F1) | EDGE_SEARCH_FINAL:48 |
| MTM | MultiTimeframeMomentum | NO SIGNALS | — | **UNTESTABLE** (not REJECTED — see F1) | EDGE_SEARCH_FINAL:49 |
| 2009 | Donchian(20), no vol filter, 8-asset pooled | dk_t=3.68 (single-asset artifact) | Pooled 8 | **REJECTED (2026-07-28, F27)** | reports/f27_pip_scaling_verification_20260728.md |
| 2010 | Donchian(20) + vol filter, 8-asset pooled | dk_t 7.93→3.32→-0.14 (jackknife) | Pooled 8 | **REJECTED (2026-07-28, F27)** | reports/f27_pip_scaling_verification_20260728.md |
| 2011 | TSM + DXY divergence, 8-asset pooled | dk_t 4.95→2.90 (inferred artifact) | Pooled 8 | **REJECTED (2026-07-28, F27)** | reports/f27_pip_scaling_verification_20260728.md |

> ⚠️ **Note on trial numbering**: trials 2009-2011 above are Path-B-numbered (`trial_ledger_b.json`) despite being technical/trend-following mechanisms, not carry/macro — they were registered in that ledger only because it had the next available slot when discovered post-hoc. See `trial_ledger_b.json`'s own notes for the full disclosure.

> ⚠️ **Note on "dk_t"**: this test statistic is referenced throughout the source documents without an inline formula definition. Before Task 0A.1, confirm and record the exact formula for `dk_t` (in `scripts/edge_search_cross_sectional.py` docstring or `CONSTITUTION.md`) so that the Phase 0A threshold (`dk_t > 2.0`) is independently verifiable — this is required for INV-012 auditability, not just internal consistency.

### Label-Shuffle Confirmation (Noise Proof — spot-check on 5 of the strategies, not full coverage)

| Case | OOS Sharpe | p-value | Verdict | Source |
|------|------------|---------|---------|--------|
| Donchian_10 XAUUSD | +0.14 | 0.375 | NO_EDGE | EDGE_SEARCH_FINAL:77 |
| Donchian_20 XAUUSD | +0.18 | 0.345 | NO_EDGE | EDGE_SEARCH_FINAL:78 |
| Donchian_55 NAS100 | -0.18 | 0.740 | NO_EDGE | EDGE_SEARCH_FINAL:79 |
| Momentum126 NAS100 | +0.48 | 0.255 | NO_EDGE | EDGE_SEARCH_FINAL:80 |
| Hybrid60 NAS100 | +0.33 | 0.295 | NO_EDGE | EDGE_SEARCH_FINAL:81 |

### Direction B — Path B: Macro/Cross-Asset (11 trials as of 2026-07-28, ALL REJECTED or UNTESTED)

| Trial | Strategy | dk_t | Pooled Sharpe | Verdict | Source |
|-------|----------|------|---------------|---------|--------|
| 2001 | PATHB-CARRY-XAUUSD | -0.977 | -0.869 | REJECTED (wrong mechanism tested — see trial_ledger_b.json) | trial_ledger_b.json |
| 2002 | PATHB-VRP-XAUUSD | -1.101 | -0.979 | REJECTED | trial_ledger_b.json |
| 2003 | PATHB-CAM-XAUUSD | 0.057 | 0.051 | REJECTED | trial_ledger_b.json |
| 2004 | PATHB-DXY-DIV-XAUUSD | -1.4327 | -1.2749 | REJECTED | trial_ledger_b.json |
| 2005 | PATHB-TSMOM-XAUUSD | -1.514 | -0.57 | REJECTED | trial_ledger_b.json |
| 2006 | PATHB-FOMC-XAUUSD | -0.984 | -0.875 | REJECTED | trial_ledger_b.json |
| 2007 | PATHB-COT-XAUUSD | -0.338 | -0.30 | REJECTED (underpowered, 40 trades) | trial_ledger_b.json |
| 2008 | PATHB-CARRY-FX-XAUUSD | — | — | UNTESTED (missing foreign rate data) | trial_ledger_b.json |
| 2009 | DONCHIAN20-8ASSET | 3.68 | 0.66 | REJECTED (F27, single-asset artifact) | trial_ledger_b.json |
| 2010 | DONCHIAN20-VOLFILTER-8ASSET | 3.32→-0.14 (jackknife) | 0.58 | REJECTED (F27) | trial_ledger_b.json |
| 2011 | TSM-DXY-DIVERGENCE-8ASSET | 2.90 | 0.50 | REJECTED (F27, inferred) | trial_ledger_b.json |

### Forex Investigation (2 REJECT, 4 INCONCLUSIVE — see F11 for handling policy; loader provenance still unknown per F24)

| Symbol | Trades | Net PnL | t-stat | Verdict | Source |
|--------|--------|---------|--------|---------|--------|
| GBPUSD | 3,388 | -$1.42 | -8.77 | REJECT | FOREX_EDGE_INVESTIGATION:20 |
| USDJPY | 3,529 | -$161 | -8.57 | REJECT | FOREX_EDGE_INVESTIGATION:21 |
| USDCAD | 1,725 | -$0.11 | -1.69 | INCONCLUSIVE (underpowered) | FOREX_EDGE_INVESTIGATION:22 |
| USDCHF | 2,498 | -$0.10 | -1.12 | INCONCLUSIVE (underpowered) | FOREX_EDGE_INVESTIGATION:23 |
| AUDUSD | 5,281 | -$0.13 | -1.55 | INCONCLUSIVE (underpowered) | FOREX_EDGE_INVESTIGATION:24 |
| NZDUSD | 5,599 | -$0.04 | -0.53 | INCONCLUSIVE (underpowered) | FOREX_EDGE_INVESTIGATION:25 |

**Total N for multiple-testing correction: 1050 (conservative) / 1033 (strict) — resolved per Task 0-Pre.1, see `reports/trial_count_reconciliation_20260720.json`.**

---

## 🔧 P0 BLOCKER INVENTORY (13 items — 12 hard live-blockers + 1 reclassified per F8)

| ID | Issue | File:Line | Live Block? | v2 Class |
|----|-------|-----------|-------------|----------|
| P0-B1 | SL/TP uses bar midpoint, not high/low | execution/fill_model.py:67-87 | YES | P0 |
| P0-B2 | Swap costs NEVER applied in backtest | backtest/engine.py:890-905 | YES | P0 |
| P0-B3 | Kill switch resets on corrupt JSON | risk/kill_switch.py:149-151 | YES | P0 |
| P0-B4 | CORS wildcard on signal_service | api/signal_service.py | YES | P0 |
| P0-B5 | webhook_receiver imports non-existent module | api/webhook_receiver.py | YES | P0 |
| P0-B6 | 3 API keys hardcoded in source | multiple files | YES | P0 |
| P0-B7 | MT5 account number in git history | .git history | YES | P0 |
| P0-B8 | Real FRED key in .env.example | .env.example | YES | P0 |
| P0-B9 | AlertManager drops ALL alerts (empty routing) | monitoring/alerts.py | YES | P0 |
| P0-B10 | Pre-trade gate not wired to live orders | execution/manager.py | YES | P0 |
| P0-B11 | Crash recovery not wired | execution/position_reconciler.py | YES | P0 |
| P0-B12 | auto_retrain returns dummy metrics | scripts/auto_retrain.py | YES | P0 |
| P0-B13 | Signal path duplicated (port 8752) | api/signal_service.py | **NO (arch)** | 🆕 **P1** — decoupled from hard gate per F8, fix opportunistically in Phase 1 but does not block Decision Gate progression |

**Status of this table as of 2026-07-28: not re-verified this session. Task 0-Pre.4 (reconciling this against the 3 other overlapping blocker inventories) remains open.**

---

## PHASE 0A: MULTI-ASSET MOMENTUM EDGE DISCOVERY (2.5 weeks — extended +2-3 days for F2/F3/F5/F12 additions)

**Status: Task 0A.1-0A.2 ALREADY EXECUTED 2026-07-20 — REJECT. See provenance note at top of document.**

**Goal:** Prove multi-asset momentum-with-ranking edge with pre-registered parameters, corrected for multiple testing and cost sensitivity
**Hard Gate (v2, expanded):**
- `dk_t > 2.0` AND `positive_sharpe >= 5` AND `label-shuffle p < 0.05` (unchanged from v1)
- 🆕 **Deflated Sharpe Ratio > 0** computed using N = reconciled trial count from Task 0-Pre (not just this one trial in isolation)
- 🆕 **PBO < 0.5** via Combinatorially Symmetric Cross-Validation (CSCV) on the backtest — moved here from Phase 2 per F6
- 🆕 **Cost-sensitivity survival**: edge must remain `dk_t > 1.5` at both 1.5x and 2.0x the assumed cost model (Pepperstone Razor + $7/rt) — per F3
- 🆕 **Jackknife robustness**: edge must not depend on any single asset — removing the single best-performing asset from the 7-asset universe, `dk_t` must remain > 1.0 — per F5

### 🆕 Naming correction (F5)
This strategy is more accurately described as **multi-asset time-series momentum with relative-ranking portfolio construction** (in the tradition of Moskowitz-Ooi-Pedersen TSMOM / Baltas multi-asset momentum), not textbook Jegadeesh-Titman cross-sectional equity momentum. This does not invalidate the hypothesis — TSMOM has strong standalone academic support — but the acceptance bar and interpretation should reflect N=7, not N=large.

### Rationale (retained from v1, reframed)
- Academic evidence: Sharpe 0.45-1.05 (Jegadeesh & Titman 1993, Moskowitz & Grinblatt 1999, Baltas 2019)
- Different mechanism: relative ranking, not absolute direction prediction
- Lower cost sensitivity: rebalance every 5 bars vs every bar (weekly vs daily)
- Code EXISTS: `strategies/momentum_factor_rotation.py`

### 🆕 Data range & regime coverage requirement (F12)
Backtest window MUST span at least 8 years and include a crisis/trend/choppy regime each. **As actually run (2026-07-20): 2005-01-03 to 2018-01-01, 12.99 years — regime_coverage confirmed crisis/trend/choppy=true in the result artifact.**

### Pre-registered Parameters (FROZEN from `momentum_factor_rotation.py:47-55`)

```python
lookbacks = (21, 63, 252)    # Multi-timeframe TSMOM (1M, 3M, 12M)
vol_target = 0.10
kappa = 2.0
top_n = 2
bottom_n = 0
rebalance_freq = 5
min_signal_strength = 0.3
```

### Pre-registered Universe
`XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30` (7 assets, D1) — as actually run 2026-07-20. **Per F23, any future re-run should use the amended 6-asset universe (drop NAS100) since it has no real cost-calibration data as of the tradeable_universe.json 2026-07-26 fix.**

### Actual Result (2026-07-20)

```
dk_t = -2.1255
pooled_sharpe = -1.5357
positive_sharpe_count = 2/7
total_trades = 3000
label_shuffle: n=200, p_value=0.0, verdict PASS (i.e. confirms no edge, not a positive finding)
combined_verdict = REJECT
```

Per-asset: XAUUSD Sharpe 0.006 (flat), XAGUSD -0.52, EURUSD -0.05, GBPUSD -0.19, USDJPY 0.017 (flat), NAS100 -1.40 (return -99.9997%), US30 -0.90 (return -95.60%). **Sanity-checked 2026-07-28**: NAS100 raw price data shows no discontinuity (max single-day move 12.6%, no split artifact); `momentum_factor_rotation.py` computes returns via direct portfolio weights, not the lot-sizing path affected by the F27 contract-spec bug. This REJECT is believed genuine, not a bug artifact.

### 🆕 Still not executed (Tasks 0A.3-0A.7)

Since the actual run predates the full v2 gate additions, **cost-sensitivity stress (0A.3), jackknife (0A.4), and PBO/DSR (0A.5) have not been run against this specific result.** Given the verdict is already a clear REJECT (dk_t=-2.13, well past the -1.5/-1.0 collapse thresholds these gates would apply on the positive side), running them is very unlikely to change the REJECT verdict and is not recommended as a priority — but if this trial is ever cited as definitively closing the multi-asset momentum question (rather than just strongly suggestive), these gates should be run for completeness.

### Go / No-Go / Marginal Decision

| Result | Action |
|--------|--------|
| **GO** (all criteria met, including all v2 additions) | Register Trial #2001, proceed to Phase 0B review + Decision Gate |
| **MARGINAL** (dk_t 1.0-2.0, some criteria met) | Document as `INSUFFICIENT_SAMPLE`, do NOT burn holdout |
| **REJECT** (dk_t < 1.0, or fails DSR/PBO/cost-stress/jackknife) | `ARCHIVE_NO_EDGE` — **this is the actual outcome as of 2026-07-20.** |

### Evidence Artifacts
```
reports/edge_search_cross_sectional_20260720.json   ✅ EXISTS — this is the actual result
reports/trial_count_reconciliation_20260720.json    ✅ EXISTS
reports/stopping_rule_trigger_citation.json         ✅ EXISTS
reports/f27_pip_scaling_verification_20260728.json  (n/a — this is a .md, not this trial's own artifact)
reports/edge_search_cost_stress_1.5x_20260720.json      NOT YET RUN for this trial
reports/edge_search_cost_stress_2.0x_20260720.json      NOT YET RUN
reports/jackknife_robustness_20260720.json               NOT YET RUN
reports/pbo_cscv_20260720.json                            NOT YET RUN
reports/deflated_sharpe_2001_20260720.json                NOT YET RUN
reports/holdout_validation_2001_20260720.json             N/A — REJECT means holdout should NOT be opened
```

---

## PHASE 0B: SPREAD MEASUREMENT + COST BASELINE (1 week, parallel with 0A review — unchanged from v1)

**Status: not started as of 2026-07-28, and arguably moot now given Phase 0A's REJECT verdict — no need to spend a week measuring spreads for a strategy that already failed on unadjusted cost.**

**Goal:** Reliable multi-session spread baseline for XAUUSD (and other metals)

```bash
python scripts/measure_spread_continuous.py \
  --symbols XAUUSD \
  --duration-days 7 \
  --output-dir data/spread_measurements/
```

### Acceptance Criteria

| Criterion | Threshold |
|-----------|-----------|
| Sessions measured | >= 21 (3 sessions x 7 days) |
| Per-session samples | >= 50 |
| Source | Live Pepperstone MT5 (not yfinance/paper) |
| Statistics computed | min, p25, median, p75, p95, max per session |

---

## PHASE 1: FIX ALL 12 HARD P0 BLOCKERS + RE-VALIDATE EDGE (3.5 weeks — extended for Task 1.14)

**Status: not started. Given Phase 0A's REJECT verdict, this phase's purpose (fix infra, then re-validate an edge that passed Phase 0A) has no edge to re-validate against. If the directional-prediction line is formally closed per the stopping rule, this phase's P0 fixes remain valuable independent of any edge (kill switch, pre-trade gate, alert routing, secrets are all correctness/safety issues regardless of strategy), but Task 1.14 (re-validate the edge) would have nothing to re-validate.**

### Task 1.1: Fix SL/TP Midpoint Bug (P0-B1)
### Task 1.2: Wire Swap Costs (P0-B2)
### Task 1.3: Hardened Kill Switch (P0-B3)
### Task 1.4: Fix AlertManager (P0-B9)
### Task 1.5: Fix webhook_receiver Import (P0-B5)
### Task 1.6: Secrets Rotation (P0-B6, B7, B8)
### Task 1.7: Wire Pre-Trade Gate to Live Path (P0-B10)
### Task 1.8: Wire Crash Recovery (P0-B11)
### Task 1.9: Fix auto_retrain Dummy Metrics (P0-B12)
### Task 1.10 (reclassified P1, F8): Unify Signal Path (P0-B13)
### Task 1.11: Remove CORS Wildcard (P0-B4)
### Task 1.12: Fix pct_change fill_method Parity
### Task 1.13: Wire Actual Spread+Commission

(Full task detail preserved from original v2 draft — file:line references and fix descriptions are in `AUDIT_INDEX.md` and the individual P0-Bxx tracking; not re-verified this session, see Task 0-Pre.4.)

### 🆕 Task 1.14: RE-VALIDATE PHASE 0A EDGE WITH CORRECTED ENGINE (F4 — mandatory, blocking)

**Moot given the REJECT verdict** — nothing to re-validate. Retained here only in case a genuinely new hypothesis passes a future Phase 0A.

---

## 🚦 DECISION GATE — MANDATORY STOP POINT (v2: 13 conditions, up from 9)

**This gate cannot be bypassed. ALL items must be true before Phase 2. Given Phase 0A's REJECT verdict, this gate is currently NOT reachable via the directional-momentum path — it would require either a successful re-registration/re-test of a genuinely new hypothesis, or abandoning the directional-prediction research line entirely per the stopping rule (see bottom of document) in favor of a structurally different edge category (e.g. funding-rate arbitrage, basis/carry, cointegration pairs).**

| # | Condition | Status as of 2026-07-28 |
|---|-----------|--------------------------|
| 1 | Trial count reconciled, stopping-rule trial IDs cited | ✅ DONE |
| 1b | Master blocker list reconciled | ❌ OPEN |
| 1c | External edge-document citations verified/classified | ⚠️ PARTIAL (4/8 spot-checked) |
| 1d | Evidence-base integrity checks passed | ✅ F15/F16 resolved, ⚠️ F17/F18 open |
| 1e | Strategy re-use blocklist / DSR reconciliation / universe amendment / warehouse audit / plan reconciliation / single-writer control | ✅ Mostly done (F21,F23,F24,F27 resolved; F22 partial; F25 partial; F26 open) |
| 2 | Cross-sectional DK t-stat > 2.0 | ❌ **FAILED — actual result -2.13** |
| 3 | Positive Sharpe count >= 5 of 7 | ❌ **FAILED — actual result 2/7** |
| 4 | Label-shuffle p-value < 0.05 | N/A given #2/#3 already fail |
| 5-9 | DSR/PBO/cost-stress/jackknife/holdout | NOT RUN (moot given clear REJECT) |
| 10 | 7-day spread measurement complete | ❌ NOT STARTED (arguably moot) |
| 11 | All 12 hard P0 blockers fixed + tested | ❌ NOT STARTED |
| 12 | Task 1.14 Re-Validation Gate PASSED | N/A |
| 13 | Human approval signed | ❌ PENDING — this is the actual decision point right now |

**Current status: Phase 0A's core gate conditions (#2, #3) have already failed. Per this document's own decision table, this means `ARCHIVE_NO_EDGE` for the multi-asset momentum hypothesis — pending explicit human sign-off to formally close it per the stopping rule below.**

---

## PHASE 2 / PHASE 3

Unreachable pending a passing Phase 0A result on some future, genuinely different hypothesis. Full detail preserved from original v2 draft (paper trading criteria, live readiness checklist, gradual scale steps) — not restated here since not currently actionable; consult `MEGA_PLAN_v2_Quant_OS_Live_Readiness.CONDENSED_20260720.md.bak` or prior conversation history if needed.

---

## 🛑 STOPPING RULE

`CONSTITUTION.md:98` — STOPPING RULE triggered: 4 consecutive p-value failures (trial IDs 1003-1006 per Task 0-Pre.2's citation).

**This plan reset the counter** via a new research direction (Multi-Asset TSMOM w/ Ranking ≠ Technical Single-Asset), on the grounds that it differs in mechanism, data requirement, academic foundation, and used pre-registered parameters, with multiple-testing correction now formally applied.

**Trial #2001/1022 (the reset attempt) has itself now REJECTED (dk_t=-2.13, 2026-07-20).**

**Per this document's own stopping-rule policy:**
1. `ARCHIVE_NO_EDGE` — this trial, all findings documented above.
2. Consider Path C — external edge import from peer-reviewed literature (e.g., TSMOM futures, carry, or funding-rate/basis edges).
3. Consider asset-class pivot (crypto-only, commodities-only).
4. **DO NOT** re-run single-asset D1 TA (already proven no edge across the reconciled trial count).
5. **DO NOT** tweak parameters after seeing results (p-hacking, forbidden by Constitution).
6. **DO NOT** ensemble REJECTED strategies.
7. **DO NOT** reuse the sacred holdout for a second attempt at the same hypothesis family — it was never opened for this REJECT (correctly preserved), and remains available for a genuinely different mechanism only.

**This is the live decision point as of 2026-07-28**: with Trial #2001/1022 REJECTED, and per prior direction from the user, the recommended next step is to formally close the directional-prediction (momentum/mean-reversion) research line and redirect effort toward structurally different mechanisms — funding-rate arbitrage, basis/carry, and cointegration pairs — which do not share this line's risk of failure (they test a market-structure question, not a direction-prediction question).

## ✅ DIRECTIONAL-PREDICTION LINE FORMALLY CLOSED (2026-07-28)

**Executed, not just recommended.** Earlier in this session the user explicitly pre-committed to this exact branch of the decision tree before Trial #2001's result was re-confirmed: *"ถ้า Trial #2001 fail (ที่ผมคาดว่าจะเป็นแบบนั้น) → ปิดสาย directional prediction ทั้งหมดอย่างเป็นทางการตาม stopping rule แล้วทุ่มเวลาที่เหลือไปที่ funding-arb + basis/carry + cointegration pairs (BTC/ETH, Gold/miner ETF)"* — i.e., if Trial #2001 fails, formally close the entire directional-prediction line per the stopping rule and redirect all remaining effort to funding-arb + basis/carry + cointegration pairs. Trial #2001 failed (REJECTED, dk_t=-2.13, confirmed 2026-07-20, verified not a bug artifact 2026-07-28). This was pre-authorized, not something decided unilaterally after the fact.

**Formal status, effective 2026-07-28:**
- **Direction A (single-asset technical, 1000-1021, 2009-2011) — CLOSED.** No further trials in this category. Every strategy file mapped to this family in `scripts/check_strategy_against_ledger.py` remains BLOCKED.
- **Direction B (macro/carry/momentum on XAUUSD-anchored universe, 2001-2011) — CLOSED.** All tested mechanisms REJECTED; trial 2008 (untested, missing data) remains formally open only pending foreign-rate data infrastructure that does not currently exist — not an active research thread.
- **Multi-asset momentum-with-ranking (Trial #2001/1022) — CLOSED.** The "reset" hypothesis this whole v2 plan was originally built around. REJECTED.
- **Redirected effort, per the user's own pre-authorized plan, now underway:**
  - Funding-rate arbitrage (Direction D) — feasibility PASS (Trial #4001), paper-trading phase started (Trial #4002), see `research/hypothesis_registry_d.json`.
  - Basis/carry (crypto, distinct from Path B's FX/XAUUSD interest-rate carry) — not yet started.
  - Cointegration pairs (BTC/ETH, Gold/miner ETF) — not yet started.

**What remains valid and unaffected by this closure:** all Phase 1 P0 safety-infrastructure fixes (kill switch, pre-trade gate, alerts, crash recovery — done 2026-07-28, see git history) remain necessary regardless of which research direction eventually produces a tradeable edge. Closing this research line is not the same as declaring the system "not worth fixing" — it narrows *what* the system should eventually trade, not whether the underlying execution/risk infrastructure needs to be correct.

---

**Generated:** 2026-07-20 (v2 review), amended 2026-07-22 (F13/F14 additions), amended again 2026-07-22 (F15-F20: third audit session's measurement-machinery integrity findings), amended again 2026-07-28 (F21-F27: strategy-reuse blocklist, DSR reconciliation, universe/data blockers, fourth-plan reconciliation, single-writer process control, ungated-positive resolution), **reconciled onto disk 2026-07-28** (this file previously lagged the working content by 8 days — see provenance note at top).
**Sources:** v1 plan + critical methodology review + reconciliation of a second independent audit session + citation verification of an external edge-research document + a third, 10-phase deep-audit session + a fourth, multi-day autonomous remediation session (2026-07-22 to 2026-07-28)
**Next Review:** Human sign-off on closing the directional-prediction line (per stopping rule above), and/or Task 0-Pre.4/F25/F26 closure.
**Supersedes:** MEGA PLAN v1.0 (`MEGA_PLAN_LIVE_TRADING_20260720.md`), `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md` (via `CHANGE_CONTROL.md` — reciprocal note not yet added, see F25), `LIVE_TRADING_READINESS_MASTER.md` (reciprocal note not yet added, see F25)
**Does NOT supersede:** `CONSTITUTION.md`, `CHANGE_CONTROL.md` (locked experiments), `AUDIT_INDEX.md`. Does NOT relate to `Meta/graxia_mega_plan_v3.md` (different document lineage, see provenance note at top).

# END OF PLAN v2
