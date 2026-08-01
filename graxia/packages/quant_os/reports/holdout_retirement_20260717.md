# Sacred Holdout — Retirement Record

**Date:** 2026-07-17
**Status:** RETIRED — superseded by `holdout_fresh_20260717.csv`

## Retired Holdout

| Field | Value |
|-------|-------|
| **File** | `data/sacred_holdout/holdout_BURNED_toy_sim_20260716.csv` |
| **Size** | 12,322 bytes |
| **SHA256** | `5a15961c15b1f4be50022b6c997418b267557beaf221c4b5769a0f9ebc9a9eed` |
| **Created** | 2026-07-16 |
| **Retired** | 2026-07-17 |

## Reason for Retirement

The old holdout was contaminated by the validation pipeline running on **toy-simulation-data** instead of the real `BacktestEngine`. Specifically:

1. `donchian_20` was tested against this holdout using a toy simulation (signal × returns × vol_mult + noise), not the real backtest engine
2. The toy simulation produced results that appeared to pass validation, but these results were not representative of actual trading behavior
3. When the same strategy was tested through the real `BacktestEngine` with pooled DK inference, it was REJECT (dk_t < 1.0)
4. Therefore, the holdout was never properly "used" in the validation sense — it was exposed to contaminated data, not a legitimate out-of-sample test

**This is not a "used and failed" retirement.** The holdout was never used in a valid way. It is retired because the pipeline that touched it was broken, not because a candidate passed or failed against it.

## Active Holdout

| Field | Value |
|-------|-------|
| **File** | `data/sacred_holdout/holdout_fresh_20260717.csv` |
| **Status** | LOCKED — never opened |
| **Date Range** | 2025-07-01 to 2026-06-29 |
| **Assets** | 7 (XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30) |
| **Rows** | 1,799 |

**No candidate has passed all gates.** The fresh holdout remains locked until a strategy passes pooled DK validation (dk_t > 2.0, ≥5 positive-sharpe assets, ≥1000 pooled trades).

## Audit Trail

| Event | Date | File |
|-------|------|------|
| Original holdout created | 2026-07-16 | `holdout_BURNED_toy_sim_20260716.csv` |
| Contamination discovered | 2026-07-17 | toy-sim pipeline identified as broken |
| Original holdout retired | 2026-07-17 | This record |
| Fresh holdout created | 2026-07-17 | `holdout_fresh_20260717.csv` |
| Fresh holdout locked | 2026-07-17 | No candidate passed gates |
