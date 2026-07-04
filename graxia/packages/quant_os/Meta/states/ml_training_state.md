# ML Training State

**Date:** 2026-06-26T16:03:30 UTC
**Script:** `scripts/train_all_models.py`

## Results

| Symbol  | Train Acc | Test Acc | Features | Bars  | Model File                        |
|---------|-----------|----------|----------|-------|-----------------------------------|
| XAUUSD  | 0.8918    | 0.4767   | 17       | 33583 | `xgboost_XAUUSD_20260626_160329.pkl` |
| EURUSD  | 0.8780    | 0.4922   | 17       | 11753 | `xgboost_EURUSD_20260626_160329.pkl` |
| US30    | 0.8806    | 0.4943   | 17       | 22301 | `xgboost_US30_20260626_160329.pkl`   |
| NAS100  | 0.8964    | 0.4785   | 17       | 30744 | `xgboost_NAS100_20260626_160329.pkl` |
| BTCUSD  | 0.8906    | 0.5109   | 17       | 45434 | `xgboost_BTCUSD_20260626_160330.pkl` |

## Failures
None — 5/5 symbols trained successfully.

## Config
- Features: 17 (returns, moving averages, ATR, RSI, volume ratio, z-scores, candle patterns)
- Model: XGBoost (100 trees, max_depth=5, lr=0.1)
- Target: 5-bar forward return >0.001 (buy), <-0.001 (sell)
- Split: last 1000 bars held out as test
