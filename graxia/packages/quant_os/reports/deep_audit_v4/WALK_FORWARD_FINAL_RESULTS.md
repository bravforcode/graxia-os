# WALK-FORWARD + LABEL SHUFFLE FINAL RESULTS

**Date**: 2026-07-06
**Fixes Applied**: target_3class leakage excluded (11 scripts), annualization factor corrected

---

## Walk-Forward Results (Corrected)

### XAUUSD H1 (11 folds, 750 OOS trades)
| Metric | Value |
|--------|-------|
| OOS Accuracy | 52.93% |
| Net PnL | **-$153,186** |
| Folds positive | 0/11 |
| Stability t-stat | -7.86 |
| Annualized Sharpe | -300 to -640 (all negative) |

### EURUSD H1 (12 folds, 650 OOS trades)
| Metric | Value |
|--------|-------|
| OOS Accuracy | 50.46% |
| Net PnL | **-$33** |
| Folds positive | 0/12 |
| Stability t-stat | -6.36 |
| Annualized Sharpe | -996 to -4071 (all negative) |

### XAUUSD M1 (from prior corrected run)
| Metric | Value |
|--------|-------|
| OOS Accuracy | 55.04% |
| Net PnL | **-$25** |
| Folds positive | 6/14 |

---

## Label Shuffling Null Test (XAUUSD H1, 100 shuffles)

| Metric | Real Model | Null (shuffled) | P-value |
|--------|-----------|-----------------|---------|
| Accuracy | 50.6% | 50.5 ± 0.9% | 0.380 (NOT significant) |
| Net PnL | -$2,017 | -$3.26M ± $917K | 0.000 (significant — but real model still loses) |
| Sharpe | -2.707 | -5408 ± 920 | 0.000 (significant — but real model still negative) |

**Interpretation**: The real model is "better than shuffled" because shuffled models actively learn wrong patterns and lose more. But the real model's accuracy (50.6%) is indistinguishable from a coin flip. **No tradeable edge exists.**

---

## Cost Perturbation (from walk-forward data)

| Cost Multiplier | XAUUSD Net PnL | EURUSD Net PnL |
|----------------|-----------------|----------------|
| 0.5× | Still negative | Still negative |
| 1× | -$153,186 | -$33 |
| 2× | More negative | More negative |
| 5× | Much more negative | Much more negative |

**Breakeven multiplier**: N/A — no edge to erode.

---

## VERDICT: NO TRADEABLE EDGE

- **23 walk-forward folds tested, 0 positive** (XAUUSD: 0/11, EURUSD: 0/12)
- **OOS accuracy ~50-53%** = random for binary classification
- **Label shuffling confirms**: real model accuracy (50.6%) is inside null distribution (50.5 ± 0.9%)
- **All prior "profitable" results were from target_3class data leakage** (100% accuracy → 50% after fix)

### Kill Criteria Assessment
- [ ] No BH-FDR-corrected feature significance → **FAILED**
- [ ] No OOS Sharpe > 0.5 with N≥500 trades → **FAILED**
- [ ] Label shuffling p-value for accuracy = 0.380 → **FAILED** (needs < 0.05)
- [ ] 0/23 folds profitable → **FAILED**

### Recommendation
**STOP trading this system as-is.** The ML model provides zero edge above random. Options:
1. **Feature engineering overhaul** — current 21 features (rsi_14, macd_diff, etc.) are commodity technical indicators with no alpha
2. **Regime-aware features** — volatility regime, market microstructure, cross-asset signals
3. **Alternative targets** — volatility forecasting, regime detection, rather than direction
4. **Accept random** — trade only on structural edges (carry, momentum from macro factors) not ML direction prediction
