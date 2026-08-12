# Bridge: Session Close — Handoff to Next Session

## What is CONFIRMED (supporting evidence exists)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| No config has significant edge | Block bootstrap CI [−$22, +$35] contains zero, t=0.56, p=0.58 | **CONFIRMED** |
| Cost bug (*2350 missing) in walk_forward.py | Fixed + regression test (6 passes) | **CONFIRMED** |
| Same bug pattern in backtest_cost.py (missing *price) | Fixed | **CONFIRMED** |
| EURUSD net negative after correct cost | −$98.60 (gross $103 − cost $202) | **CLOSED** |
| accuracy×net_pnl per-fold r=0.656 | Strong linear relationship | **CONFIRMED** |
| 25.3% folds have accuracy<0.5 | 42/166 folds | **CONFIRMED** |
| ATR×accuracy weak relationship | rho=−0.19, d=0.235, block permutation p=0.0155 | **REAL BUT TOO WEAK TO ACT ON** |
| 16/20 worst folds driven by accuracy failure, 4/20 by R:R failure | Overlap analysis | **CONFIRMED** |
| Session is NOT a reliable predictor of worst folds | Base rate comparison (bottom 20 vs all 166) | **CONFIRMED** |
| ForexFactory calendar does not exist on disk | Glob search returned empty | **CONFIRMED** |
| No holdout subset remains clean in historical data | Every fold used in ≥1 aggregate stat | **CONFIRMED — prospective only** |

## What is WITHDRAWN (no evidence)

| Claim | Evidence | Status |
|-------|----------|--------|
| "~40 fold periodicity" | No pattern found | **WITHDRAWN** |
| "NY session dominates worst folds" | Bottom 20 matches base rate | **WITHDRAWN** |
| "oos_acc is ex-ante proxy for confidence" | Post-hoc, needs labels | **WITHDRAWN → reclassified BLOCKED** |
| "Clean holdout exists in historical data" | Every fold contaminated | **WITHDRAWN** |

## Path Status (Post-Gate)

| Path | Status | Why |
|------|--------|-----|
| A1: ATR regime filter | **DEAD** | rho=−0.19, d=0.235 — too weak |
| A: General accuracy-failure fix | **NO FIX IDENTIFIED** | Session, ATR, calendar all dead ends |
| B1/C3: mag_pred-based TP/sizing | **BLOCKED** | Gate #2: mag_pred not saved per trade |
| Conf-based regime filtering | **BLOCKED** | Gate #3: confidence not saved per trade |
| Historical holdout validation | **IMPOSSIBLE** | No clean subset remains |

## ✅ Instrumentation Complete

`walk_forward.py` now saves per-trade Parquet alongside aggregate JSON:
- **File**: `per_trade_{symbol}_{freq}_{train}w_{test}t_conf{conf}.parquet`
- **Schema**: fold, timestamp, direction, confidence, mag_pred, realized_return, expected_profit, trade_selected, target
- **Run completed**: `artifacts/walk_forward_v4/` — 33,200 rows, 166 folds
- **Aggregate results identical to v3_fixed** (net +$1,303.52, t=0.56) — zero regression

## Session Handoff

Next session can proceed directly to analysis (no infra work needed):

1. **Compute** `correlation(mag_pred, realized_return)` on per-trade Parquet — Gate #2 viability for B1/C3
2. **Compute** `correlation(confidence, is_correct)` — Gate #3 viability for conf-based regime filter
3. **Pre-register** pass criteria (t≥2 on block bootstrap CI, holdout = prospective data only)
4. **If either gate passes**: design filter/sizing → prospective paper trading
5. **If neither gate passes**: accuracy drop may be structural limitation of feature set — requires fundamentally different features or strategy design, not filter tuning

Existing artifacts for Gate analysis:
- `artifacts/walk_forward_v4/per_trade_XAUUSD_15min_500w_200t_conf0.85.parquet` (new)
- `artifacts/walk_forward_v4/wf_XAUUSD_15min_500w_200t_conf0.85.json` (same as v3_fixed)
