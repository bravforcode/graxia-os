# Pre-Registration — Trial 9001: Forex 4-Pair Directional Retest (Direction H)

**Status:** RESOLVED — REJECTED 2026-08-06 (verdict stamped with provenance)
**Direction H** (`reports/stopping_rule_2026_08_06_direction_h.md`, ledger `research/trial_ledger_h.json`)

## RESULT (2026-08-06)

| Pair | Trades | Net PnL | t-stat | Verdict |
|------|--------|---------|--------|---------|
| USDCAD | 1,901 | -$1.61 | **-8.15** | REJECT |
| USDCHF | 2,749 | -$1.72 | **-8.94** | REJECT |
| AUDUSD | 6,012 | -$2.86 | **-16.27** | REJECT |
| NZDUSD | 6,215 | -$2.78 | **-17.41** | REJECT |

**Original INCONCLUSIVE verdicts RESOLVED → REJECT.** With measured FROM_TICKS
costs and a powered design (min_confidence 0.55, 1,901-6,215 trades per pair,
247 folds), every pair loses **significantly** (t = -8.2 to -17.4) — the
mechanism is a structural failure, not underpowered, not a cost artifact.
Direction H consecutive-fail count: 1/3 (stopping rule §4.4).

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

## Frozen parameters (LOCKED 2026-08-06 — no tuning after this point)

- **Runner**: `scripts/run_multi_instrument_wf.py` (canonical walk-forward, `validation/walk_forward.py`)
- **Mechanism**: XGBoost binary classification of next-bar direction on the runner's FIXED feature set
  (return_1/5/10/20, vol_10/20, vol_ratio, atr_14, atr_ratio, rsi_14, rsi_normalized, macd,
  macd_signal, macd_hist, bb_width, bb_position, session flags) — SAME feature family as the
  original 2026-07-12 batch (loader provenance resolved: `run_multi_instrument_wf.py`)
- **Timeframe**: H1 (8.1y, meets F12 >= 8y; M15 rejected — only 2.5y exists)
- **Instruments**: USDCAD, USDCHF, AUDUSD, NZDUSD (4 underpowered pairs; GBPUSD/USDJPY already
  conclusively REJECTED — not retested)
- **Data**: `data/{SYM}_H1.csv` (50,000 bars, 2018-06 → 2026-07)
- **Model params**: n_estimators=100, max_depth=5, learning_rate=0.1, subsample=0.8,
  colsample_bytree=0.8, random_state=42, eval_metric=logloss
- **WF windows**: train=500, test=200, step=200, purge=14, embargo=0 (unchanged from original)
- **MIN_CONFIDENCE: 0.65 → 0.55** (CHANGED from original — pre-registered to raise
  trades/fold from ~7 to ~20+; the 0.65 filter produced underpowered folds (1,725-5,599
  trades over 247 folds ≈ 7/fold). 0.55 is frozen identically across all 4 pairs — NOT
  per-pair tuning, NO lookahead at results)
- **min_expected_profit**: 0.0005 (unchanged)
- **Costs**: measured FROM_TICKS from config/cost_calibration.json (USDCAD 14.14 rt bps,
  USDCHF 14.25, AUDUSD 14.28, NZDUSD 14.68) — `--allow-default-costs` FORBIDDEN (the original
  batch ran 5/6 pairs on UNMEASURED defaults spread=1e-05/slippage=3e-05, which invalidated
  its INCONCLUSIVE verdicts as evidence; retest must use real costs)

## Verdict logic (runner `determine_verdict`, unchanged)

PROMOTE if positive_pct>0.6 & net>0 & |t|>=1.5; CONDITIONAL if positive_pct>0.4 & net>0;
REJECT if |t|>=2.0 & net<0; INCONCLUSIVE if |t|<2.0.

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

`reports/stopping_rule_2026_08_06_direction_h.md` (created at freeze time):
4 consecutive REJECTED trials across the 4 pairs (one per pair) triggers direction stop,
or early stop if cumulative DSR drops below threshold mid-run.

## Provenance

Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=9001, id=DIRH-FOREX4-H1). Pre-registration discipline (F27): this file exists
BEFORE any backtest runs — FROZEN 2026-08-06 prior to execution.

## Sacred holdout

NOT used (LOCKED, Phase 4.5 only).

## Post-freeze record

- FROZEN 2026-08-06 (min_confidence 0.65→0.55 pre-registered; measured costs mandatory).
- All open items from the DRAFT resolved at freeze: runner identified, costs measured,
  min_confidence fixed, stopping rule + ledger created, trial 9001 registered via
  auto_increment.
