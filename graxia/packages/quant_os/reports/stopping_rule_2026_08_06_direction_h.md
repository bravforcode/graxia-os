# Stopping Rule — Direction H (Forex 4-Pair Walk-Forward Retest) — Pre-Registration

**Status:** LOCKED — 2026-08-06
**Supersedes for future trials:** nothing (new direction; Direction G stopped 2026-08-06 §4.4)
**SHA-256 of this file:** recorded in `research/trial_ledger_h.json` → `lock_doc_sha256` at lock time (same self-reference-avoidance convention as the 08-05 document)
**Cumulative trial count at lock:** 0 (separate ledger per Path-B/D/G precedent)

---

## 0. This document opens a NEW direction — stated plainly

Direction D (`stopping_rule_2026_07_30.md`) and Direction G
(`stopping_rule_2026_08_05.md`) both excluded the 4 pairs USDCAD/USDCHF/AUDUSD/NZDUSD
with the reason: **no cost data at all** (testing an edge net of an assumption).

That exclusion is now **resolved for all 4 pairs**: real tick-derived cost
calibration exists as of 2026-08-06 (`config/cost_calibration.json`, all 4
`FROM_TICKS`, measured from 230k-455k ticks each via `mt5.copy_ticks_range`,
broker source recorded; see `scripts/calibrate_forex4_from_ticks.py`).

This document therefore opens **Direction H** for these 4 pairs with a
**re-test of the original 2026-07-12 walk-forward batch** — whose INCONCLUSIVE
verdicts were invalid as evidence for two reasons, both now fixed:
1. **F24 loader provenance gap** — runner and artifact were unlocatable; now
   resolved: `scripts/run_multi_instrument_wf.py` →
   `artifacts/wf_13_instruments/wf_batch_H1_20260712_200555.json`.
2. **Unmeasured default costs** — 5/6 pairs ran with `--allow-default-costs`
   (spread=1e-05, slippage=3e-05); retest runs on measured FROM_TICKS costs
   with `--allow-default-costs` FORBIDDEN.
3. **Underpowered folds** — 50k-bar H1 cap + min_confidence=0.65 gave ~7
   trades/fold; retest freezes min_confidence=0.55 (same for all 4 pairs,
   pre-registered, no per-pair tuning).

Per F11 (MEGA_PLAN:37), INCONCLUSIVE verdicts are not formal failures — Trial
9001 is a NEW hypothesis with real costs and a powered design, not a re-run.

---

## 1. Scope — instruments & mechanisms

| Trial (pre-registered) | Instrument | Mechanism |
|---|---|---|
| 9001 | USDCAD, USDCHF, AUDUSD, NZDUSD (H1) | XGBoost next-bar-direction classifier, fixed feature set (return/vol/ATR/RSI/MACD/BB/session), walk-forward purge+embargo |

**Cost basis (measured, FROM_TICKS, 2026-08-06):**

| Symbol | spread_bps (median) | commission_bps | round_trip_bps |
|---|---|---|---|
| USDCAD | 0.071 | 7.0 | 14.14 |
| USDCHF | 0.124 | 7.0 | 14.25 |
| AUDUSD | 0.142 | 7.0 | 14.28 |
| NZDUSD | 0.341 | 7.0 | 14.68 |

Slippage: runner models slippage as half of round-trip return (cost
calibration convention used by the original batch). No fabricated 0.0.
Registry entries MUST use `research/registry_schema.stamp_trial_entry()` so
provenance is written at registration time.

## 2. Scope — methodology

Gate stack carries over unchanged from Direction D (p-value, WFA-OOS, WFE,
DSR, PBO-CSCV, bootstrap CI, min-independent-trades >= 100). Verdict logic is
the runner's frozen `determine_verdict` (PROMOTE/CONDITIONAL/REJECT/
INCONCLUSIVE). Regime conditioning remains OUT OF SCOPE (same reasoning as
07-30 §2 — don't stack methodology changes).

## 3. Trial budget

- **New hypothesis budget:** 25 (same size as Path-B allowance — not enlarged)
- **Trial range:** 9000–9999 (free block per `TRIAL_ID_RANGES.md`)
- **Separate ledger:** `research/trial_ledger_h.json` + `research/hypothesis_registry_h.json` (Path-B/D/G precedent)

## 4. Stopping conditions (carried over from 07-30 §3)

Research under this direction stops when **any** of:
- **4.1** New hypothesis count reaches 25.
- **4.2** 3 months elapse from this lock date (deadline: 2026-11-06).
- **4.3** 80 research-hours are logged against this direction.
- **4.4** 3 consecutive hypotheses fail at the same gate — stop and re-examine calibration, data quality, or framing.

## 5. Preconditions

1. Trial 9001 may be PRE-REGISTERED now (this document + ledger + registry).
2. Verdicts MUST be stamped with provenance (`registry_schema.stamp_trial_entry`).
3. Costs MUST be the measured FROM_TICKS entries — `--allow-default-costs` is FORBIDDEN.
4. Sacred holdout (`data/sacred_holdout/`) stays LOCKED — unlock Phase 4.5 only.

## 6. Acknowledgment

By locking this document:
1. This opens a new direction whose 4 instruments were previously excluded
   for lack of cost data; that blocker is now resolved with real tick-derived
   measurements (2026-08-06).
2. Budget is 25 hypotheses in a separate ledger — it does NOT touch the main
   ledger cap or Direction D/G budgets.
3. GBPUSD and USDJPY are NOT retested — they were conclusively REJECTED in
   the original batch (t=-8.77, t=-8.57) and remain closed.
4. min_confidence change (0.65→0.55) is pre-registered identically across all
   4 pairs; no per-pair tuning, no lookahead at results.
5. Regime conditioning is deliberately excluded to avoid compounding
   methodology changes.
