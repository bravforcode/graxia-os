# Pre-Registration — Trial 9001: Forex 4-Pair Directional Retest (Direction H)

**Status:** DRAFT — 2026-08-06 (for human review; becomes FROZEN only after approval + ledger registration)
**Direction H** (new direction — stopping rule `reports/stopping_rule_2026_08_06_direction_h.md` to be created at freeze time; ledger `research/trial_ledger_h.json` to be created at freeze time)

## Background / motivation (why this trial exists)

The original 6-pair forex batch (`artifacts/wf_13_instruments/wf_batch_H1_20260712_200555.json`,
runner `scripts/run_multi_instrument_wf.py`) produced 2 REJECT (GBPUSD t=-8.77, USDJPY t=-8.57)
and 4 **INCONCLUSIVE-underpowered** verdicts:

| Pair | Trades | t-stat | Original status |
|------|--------|--------|-----------------|
| USDCAD | 1,725 | -1.69 | INCONCLUSIVE (underpowered) |
| USDCHF | 2,498 | -1.12 | INCONCLUSIVE (underpowered) |
| AUDUSD | 5,281 | -1.55 | INCONCLUSIVE (underpowered) |
| NZDUSD | 5,599 | -0.53 | INCONCLUSIVE (underpowered) |

Two integrity problems invalidate those verdicts as evidence (NOT as strategy proof):
1. **Loader provenance was lost** (MEGA_PLAN v2 F24) — now resolved: runner and artifact located (2026-08-06).
2. **5/6 pairs ran with `--allow-default-costs`** (unmeasured spread=1e-05, slippage=3e-05) because
   no cost entry existed for them — the doc's "cost dominance" narrative was never actually modeled.
   Underpoweredness root cause: 50,000-bar H1 cap + `min_confidence=0.65` → ~7 trades/fold.

Per F11 (MEGA_PLAN:37), INCONCLUSIVE is not counted as a formal failure — this is a NEW hypothesis
with measured costs and a powered design, not a re-run of the old one.

## Hypothesis

H1 trend-continuity signals on USDCAD/USDCHF/AUDUSD/NZDUSD (same mechanism class as the original
batch — breakout/momentum continuity) produce positive net-of-measured-cost edge. The original
verdicts are uninformative (unmeasured costs + underpowered folds), so this trial tests the
mechanism on these pairs with FROM_TICKS costs and a sample large enough to resolve |t| >= 2
with power 0.8 at the expected effect size.

## Frozen parameters (no tuning after freeze)

- Mechanism: identical family to the original batch — directional momentum/breakout continuity
  (exact rule frozen at freeze time from `run_multi_instrument_wf.py` baseline; NO parameter
  selection after this point)
- Timeframe: H1 (data already satisfies >= 8 years; M15 rejected — only 2.5y history exists)
- Instruments: USDCAD, USDCHF, AUDUSD, NZDUSD (the 4 underpowered pairs; GBPUSD/USDJPY already
  conclusively REJECTED — do not retest)
- Data: `data/{SYM}_H1.csv` (2018-06 → 2026-07, ~8.1y, meets F12 >= 8y)
- Sample sufficiency: pre-registered minimum independent trades = 100 (template gate);
  design targets 40+ trades/fold (raise the 50k-bar cap and/or lower min_confidence from 0.65
  to a pre-registered level — recorded in the frozen params, not tuned)

## Costs (measured, FROM_TICKS 2026-08-06 — NEW)

| Pair | Spread median (bps) | Commission (bps) | Round trip (bps) |
|------|--------------------:|-----------------:|-----------------:|
| USDCAD | 0.0713 | 7.0 | 14.14 |
| USDCHF | 0.1237 | 7.0 | 14.25 |
| AUDUSD | 0.1422 | 7.0 | 14.28 |
| NZDUSD | 0.3407 | 7.0 | 14.68 |

Source: `scripts/backfill_ticks_shortcut.py` (MT5 copy_ticks_range 2026-07-31→08-05) +
`scripts/calibrate_forex4_from_ticks.py` → `config/cost_calibration.json` entries USDCAD/USDCHF/AUDUSD/NZDUSD
(344k/243k/285k/231k quote ticks, ask>bid filtered). Slippage: fill-simulator P90 to be added at
calibration completeness (currently null — honest). **No default-cost fallback allowed.**

## Gate stack (unchanged from Direction D/G)

p<0.05 OOS, WFA-OOS >= 70%, WFE >= 0.5 & < 1.5, DSR > 0.95 (cumulative N), PBO-CSCV < 0.5,
bootstrap CI excludes 0, min-independent-trades >= 100 (see reports/stopping_rule_2026_08_05.md).

## Stopping rule (Direction H)

Pre-registered at freeze time in `reports/stopping_rule_2026_08_06_direction_h.md`:
4 consecutive REJECTED trials across the 4 pairs (one per pair) triggers direction stop,
or early stop if cumulative DSR drops below threshold mid-run.

## Provenance

Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=9001, id=DIRH-FOREX4-H1). Pre-registration discipline (F27): this file exists
BEFORE any backtest runs.

## Sacred holdout

NOT used (LOCKED, Phase 4.5 only).

## Open items before freeze (human review)

1. Exact frozen rule parameters (from run_multi_instrument_wf.py baseline, no selection).
2. Min-confidence / bar-cap change to reach 40+ trades/fold — freeze the number.
3. Create `reports/stopping_rule_2026_08_06_direction_h.md` + `research/trial_ledger_h.json`.
4. Add slippage P90 from fill simulator (fill_samples per pair) or record null honestly.
5. Trial number confirmation via `scripts/auto_increment_trial.py`.
