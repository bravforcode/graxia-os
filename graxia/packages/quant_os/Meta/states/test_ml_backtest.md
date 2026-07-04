# ML Models + Backtest Suite — Full Verification

**Date:** 2026-06-26 16:48 UTC
**Environment:** Windows, Python 3.x, quant_os

---

## 1. Models Directory Inventory

16 `.pkl` files in `ml/models/`:

| Group | Count | Details |
|-------|-------|---------|
| Legacy (Jun 19) | 8 | 4 models × 2 training runs; 34 features each |
| Multi-symbol (Jun 26) | 5 | XAUUSD, EURUSD, US30, NAS100, BTCUSD; 17 features each |
| Live (Jun 26) | 3 | Latest: `xgboost_live_20260626_161034.pkl` |

---

## 2. All Models Load Test — PASS ✅

16/16 models loaded successfully as `XGBClassifier`.

- 8 legacy models: **PASS** (34 features, `test_acc=?` — no accuracy key in dict)
- 5 multi-symbol models: **PASS** (17 features, test_acc reported)
- 3 live models: **PASS** (raw XGBClassifier, no wrapping dict)

**Failures:** 0

---

## 3. Training Results Summary

| Symbol   | Train Acc | Test Acc | Bars   | Features |
|----------|-----------|----------|--------|----------|
| XAUUSD   | 0.8918    | 0.4767   | 33,583 | 17       |
| EURUSD   | 0.8780    | 0.4922   | 11,753 | 17       |
| US30     | 0.8806    | 0.4943   | 22,301 | 17       |
| NAS100   | 0.8964    | 0.4785   | 30,744 | 17       |
| BTCUSD   | 0.8906    | 0.5109   | 45,434 | 17       |

✅ All train acc > 87%
⚠️ Test acc near 0.5 (coin-flip level) — significant overfitting gap (~40pp)

---

## 4. Paper Trade Bot Model Loading — PASS ✅

Loaded `xgboost_live_20260626_161034.pkl` as `XGBClassifier` (raw model, no dict wrapper). Matches `paper_trade_bot.py` loading pattern.
⚠️ No accuracy/features metadata embedded in this model (raw pickle, not dict-wrapped).

---

## 5. Multi-Symbol Model Loading — PASS ✅

All 5 target symbols have dedicated models:

| Symbol | Model File | Status |
|--------|-----------|--------|
| XAUUSD | `xgboost_XAUUSD_20260626_160329.pkl` | ✅ Loaded |
| EURUSD | `xgboost_EURUSD_20260626_160329.pkl` | ✅ Loaded |
| US30   | `xgboost_US30_20260626_160329.pkl`   | ✅ Loaded |
| NAS100 | `xgboost_NAS100_20260626_160329.pkl` | ✅ Loaded |
| BTCUSD | `xgboost_BTCUSD_20260626_160330.pkl` | ✅ Loaded |

All 5 models: `XGBClassifier`, 17 features.

---

## 6. Backtest Suite Results — PASS ✅

Ran `scripts/backtest_suite.py` on 7 forex/indices/crypto symbols, 60,000 15m bars each.

### Best Strategy Per Symbol

| Symbol | Best Strategy | Sharpe | Regime |
|--------|-------------|--------|--------|
| XAUUSD | Momentum     | 1.31   | trending/normal |
| EURUSD | MeanReversion | 1.82  | ranging/normal |
| GBPUSD | MeanReversion | 1.38  | ranging/normal |
| USDJPY | TrendFollow  | 1.30   | trending/normal |
| US30   | MeanReversion | 0.35  | trending/low_vol |
| NAS100 | Momentum     | 0.94   | trending/low_vol |
| BTCUSD | RSI          | 0.56   | trending/low_vol |

### Key Observations
- **Best overall:** EURUSD MeanReversion (Sharpe 1.82, Return 13.9%)
- **Floor strategies:** VolBreakout returns 0% on all symbols (never triggers)
- **Worst:** BTCUSD Momentum (Sharpe -0.50, Return -48.9%) — crypto momentum fails
- **Regime correlation:** MeanReversion dominates ranging regimes; Momentum/TrendFollow dominate trending regimes
- **US30/BTCUSD/NAS100** (low_vol regime) have uniformly weaker Sharpe across all strategies

Result file: `results/backtest_suite_20260626_164814.json`

---

## 7. Issues & Warnings

| Issue | Severity | Detail |
|-------|----------|--------|
| Test acc ≈ 0.5 | ⚠️ | All 5 trained models show ~40pp train/test gap (overfitting) |
| `artifacts/strategy_model/` missing | ⚠️ | Paper trade bot falls back to `ml/models/` — works, but expected path absent |
| `results/` dir created on-demand | ℹ️ | First run creates the directory |
| Legacy models (34 feats) no test_acc | ℹ️ | Older training run didn't store accuracy in pickle dict |

---

## Overall Verdict

**PASS** ✅ — All ML models (16/16) load correctly, backtest suite runs to completion on all 7 symbols, paper_trade_bot and multi_symbol_bot loading patterns work. Model quality (test acc ~0.48-0.51) and overfitting need attention, but infrastructure is functional.
