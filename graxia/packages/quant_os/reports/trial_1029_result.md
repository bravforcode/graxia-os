# Trial #1029: Regime-Adaptive Multi-Asset — REJECTED

**Date**: 2026-07-30
**Status**: REJECTED (1/5 gates)
**Strategy**: Volatility-based regime detection across 7 assets

---

## Executive Summary

The regime-adaptive multi-asset strategy was designed to address the root cause of all previous strategy failures: **single-asset dependency**. The approach uses volatility-based regime detection (low-vol = momentum, high-vol = mean-reversion) across 7 assets simultaneously.

**Result**: REJECTED. The strategy exhibits the same single-asset dependency pattern as all previous strategies, this time on NAS100.

---

## Key Evidence

### Performance Metrics
| Metric | Value | Gate | Status |
|--------|-------|------|--------|
| Driscoll-Kraay t-stat | 0.3327 | > 2.0 | FAIL |
| Sharpe ratio | 0.3864 | > 1.0 | FAIL |
| Max drawdown | -3.83% | > -25% | PASS |
| Win rate | 50.60% | > 50% | PASS |
| Profit factor | 1.351 | > 1.1 | PASS |
| Trade count | 300 | > 100 | PASS |
| Walk-forward efficiency | 0.0 | > 0.3 | FAIL |
| Jackknife sign flip | YES | NO | FAIL |

### Walk-Forward Analysis
| Window | IS Sharpe | OOS Sharpe | WFE |
|--------|-----------|------------|-----|
| 1 | -0.938 | 0.000 | -0.000 |
| 2 | 0.538 | 0.000 | 0.000 |
| 3 | 0.512 | 0.000 | 0.000 |

**Average WFE**: 0.000 (FAIL — no out-of-sample edge)

### Jackknife Leave-One-Out
| Excluded Asset | Sharpe | Delta | % Change |
|----------------|--------|-------|----------|
| Baseline | 0.386 | — | — |
| XAUUSD | 0.477 | -0.091 | -23.5% |
| XAGUSD | 0.570 | -0.184 | -47.5% |
| EURUSD | 0.596 | -0.210 | -54.3% |
| GBPUSD | 0.418 | -0.031 | -8.1% |
| USDJPY | 0.626 | -0.239 | -62.0% |
| **NAS100** | **-0.066** | **+0.452** | **+117.0%** |
| US30 | 0.279 | +0.107 | +27.8% |

**Critical finding**: Excluding NAS100 flips Sharpe from +0.386 to -0.066. The strategy is entirely dependent on NAS100.

### Regime Distribution
- Normal: 84.4%
- Low-vol: 8.3%
- High-vol: 7.3%

---

## Root Cause Analysis

### Why This Strategy Failed

1. **Single-asset dependency (NAS100)**: The strategy's entire edge comes from NAS100 momentum. When NAS100 is excluded, the strategy loses money.

2. **No out-of-sample edge**: Walk-forward OOS Sharpe = 0.0 across all windows. The in-sample performance is entirely overfit.

3. **Low statistical significance**: dk_t = 0.33 ≪ 2.0. The pooled result is not statistically different from zero.

4. **Same pattern as all rejected strategies**: Every strategy in the quant_os ledger has exhibited this pattern — appears to have edge in-sample, but edge disappears with single-asset exclusion or out-of-sample testing.

### The Fundamental Problem

The academic literature suggests regime-switching should work, but:
- Our regime detection is too slow (200-day lookback for volatility)
- The regime thresholds may be wrong for these specific assets
- The universe (7 diverse assets) may not have enough correlation to benefit from regime switching
- Transaction costs from frequent regime switching may eat any edge

---

## Files Created/Modified

| File | Action |
|------|--------|
| `strategies/regime_adaptive_multi_asset.py` | NEW — Strategy implementation |
| `scripts/test_ram_strategy.py` | NEW — Basic test script |
| `scripts/validate_ram_strategy.py` | NEW — Full validation battery |
| `research/pre_registration/trial_1029_regime_adaptive_multi_asset.md` | NEW — Pre-registration document |
| `research/hypothesis_registry.json` | UPDATED — Added trial 1029 (REJECTED) |
| `research/trial_ledger.json` | UPDATED — Next available: 1030 |
| `reports/ram_trial_1029.json` | NEW — Basic results |
| `reports/ram_trial_1029_full_validation.json` | NEW — Full validation results |

---

## Lessons Learned

1. **Single-asset dependency is the #1 killer**: Every strategy fails because of one asset. Need to find strategies where edge is genuinely distributed.

2. **Walk-forward OOS Sharpe = 0.0 is a death sentence**: If the strategy has zero edge out-of-sample, it's overfit.

3. **Jackknife sign flip is the strongest rejection signal**: When excluding one asset flips the sign of Sharpe, the strategy is not robust.

4. **Regime detection may not work for diverse universes**: The 7 assets we chose (forex, metals, equities) may not have enough correlation to benefit from regime switching.

5. **The fundamental problem remains**: We have not found a strategy where edge is genuinely distributed across multiple assets. Every strategy is a single-asset bet in disguise.

---

## Next Steps

1. **Consider different universes**: Maybe regime switching works for more correlated assets (e.g., all forex, or all precious metals).

2. **Consider different regime detection**: Maybe VIX-based or correlation-based regime detection works better.

3. **Consider simpler approaches**: Academic literature suggests simple diversification beats optimization. Maybe the answer is not regime switching but simple equal-weight across uncorrelated assets.

4. **Accept no edge**: The honest conclusion after 15+ rejected strategies is that there may be no deployable edge in this system. This is a valid and important finding.
