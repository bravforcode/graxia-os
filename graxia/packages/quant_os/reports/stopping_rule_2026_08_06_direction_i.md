# Stopping Rule — Direction I (EA Deep-Mine Funnel) — Pre-Registration

**Status:** LOCKED — 2026-08-06
**SHA-256 of this file:** recorded in `research/trial_ledger_i.json` → `lock_doc_sha256` at lock time (same self-reference-avoidance convention as prior directions)
**Cumulative trial count at lock:** 0 (separate ledger per Path-B precedent — `trial_ledger_i.json`)

---

## 1. Scope — what this direction is

Direction I opens the **EA Deep-Mine Funnel** (spec: `docs/superpowers/specs/2026-08-06-direction-i-ea-funnel-design.md`):

- **Instruments:** the 23-symbol universe (per `config/tradeable_universe.json` main section, pinned AFTER Tier0 Sweep Sub-project C1 commit — spec A12), all timeframes M1-MN1
- **Mechanisms:** mined from all sources (MQL5, GitHub, MyFxBook, Forex Factory, TradingView, academic, institutional/obscure) → taxonomy → screening → pre-registered trials. Martingale/grid only via the hard gate (spec §4)
- **Scope partition:** mechanism families owned by parallel Direction H (forex4 H1 trend-continuity CLOSED; forex4 RSI MR WATCH; EURUSD H4 WATCH) are citations-only — spec §1.8, A17
- **Trial numbering:** 10000-10999 (per `TRIAL_ID_RANGES.md`, next free 1000-block)

## 2. Methodology

Gate stack carries over from Direction D/G (p-value HAC/NW, WFA-OOS, WFE, DSR, PBO-CSCV, bootstrap CI, min-independent-trades) — tiered G1/G2/G3 per spec §8 (A4). Costs MUST be FROM_TICKS for trials; screening uses conservative proxies (asset-class worst-case ×1.5) and survivors are re-filtered at real costs (A1). Regime conditioning is a separate sub-program (I.1) — no mid-direction methodology stacking.

## 3. Budget

- **New hypothesis budget:** 40 (hard cap across ALL cycles C1/C2/C3 AND all sub-programs — A2/A15)
- **Trial range:** 10000-10999
- **Separate ledger:** `research/trial_ledger_i.json` + `research/hypothesis_registry_i.json` + `research/screening_log_i.json`
- **N accounting:** N_I = 1050 (reconciled baseline) + distinct screening configs + trials in ledger I (spec §3, A6) — via `validation/n_trials_i.py`

## 4. Stopping conditions

Research under this direction stops when **any** of:
- **4.1** New hypothesis count reaches 40.
- **4.2** ~~3 months elapse~~ **REMOVED by user override 2026-08-06 (no time limit).**
- **4.3** 400 research-hours are logged against this direction.
- **4.4** 3 consecutive hypotheses fail at the same gate — **stop C1 immediately, joint-cause analysis, human decision** among: (a) pivot to P5 data infrastructure then restart C1, (b) amend funnel parameters (documented, pre-registered), (c) terminate Direction I. No automatic default (spec §2.1, A5).

## 5. Preconditions

1. Trials MAY be pre-registered now (this document + registries).
2. Verdicts MUST be stamped with provenance (`registry_schema.stamp_trial_entry`).
3. Slippage MUST come from fill-simulator P90 — `slippage_source: "none"` only if the runner honestly does not model slippage (never 0.0).
4. Sacred holdout (`data/sacred_holdout/`) stays LOCKED — unlock Phase 4.5 (P7) only.
5. EURUSD H4 candidate pre-registration waits for Tier0 Sweep Sub-project B decision (spec §1.7, A9).
6. Writer-lock enforcement active: pre-commit hook `writer-lock-check` (scripts/check_writer_lock.py, A18) — commits refused while a live foreign lock exists.
7. Direction H files are NEVER modified by this direction (citations-only, A16/A17).

## 6. Acknowledgment

By locking this document:
1. This opens a new direction whose block (10000-10999) is the next free per TRIAL_ID_RANGES.md — ranges follow creation order, not alphabetical order (A13).
2. Budget is 40 hypotheses in a separate ledger — it does not touch the main ledger cap or Direction H's ledger.
3. Parallel Direction H (9000-9999) executes independently under its own rules; this direction absorbs its verdicts as citations only.
4. User override recorded: no deadline; 400 research-hours; escalation checkpoint when ≤10 trials remain (A15).
