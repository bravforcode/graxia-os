# Deep Research: Algorithmic & Statistical Gaps in quant_os (Post Phase 4)

**Date**: 2026-07-04  
**Status**: COMPLETE  
**Researcher Agent**: ruflow-researcher

---

## Executive Summary

After thorough codebase analysis and web research, the quant_os system has **strong foundations** in CPCV, DSR, and bootstrap CI — but has **5 critical gaps** that remain unaddressed. These gaps could cause false-positive strategy validation, unrealistic backtest performance, and production risk.

---

## GAP 1: White's Reality Check / Hansen's SPA Test — MISSING (HIGH)

**What it is**: White (2000) Reality Check and Hansen's (2005) SPA are the standard tests for evaluating whether ANY strategy in a universe of N strategies beats the null distribution of "best random strategy". This is critical for strategy universe evaluation — when you test 100+ parameter combinations, you need to know if the best one is genuine or selection bias.

**Current state**: 
- `validation/deflated_sharpe.py` has DSR (parametric, assumes normal returns)
- `validation/multiple_testing.py` has Benjamini-Hochberg FDR control
- **Neither implements White's bootstrap-based Reality Check or Hansen's SPA**

**Why DSR alone is insufficient**:
- DSR assumes normal return distribution (parametric)
- Reality Check / SPA use bootstrap to generate the null distribution of the BEST strategy's performance
- SPA is more powerful than Reality Check (accounts for correlation between strategies)
- For non-normal returns (fat tails, skewness common in FX), bootstrap-based tests are statistically superior

**Severity**: HIGH — Without this, the system cannot properly evaluate strategy universes or distinguish genuine alpha from overfitting in multi-strategy/multi-parameter contexts.

**Implementation approach**:
- Add `validation/reality_check.py` with White's Reality Check (bootstrap)
- Add `validation/spa_test.py` with Hansen's SPA (stationary bootstrap)
- Both should reuse existing `stationary_bootstrap()` from `backtest/metrics.py`
- Integrate into `OverfittingDetector` as an 8th check alongside DSR

---

## GAP 2: CPCV — EXISTS but incomplete (MEDIUM)

**Current state**: 
- `core/cross_validation.py` has FULL CPCV implementation with purging + embargo
- `combine_purged_k_fold_cv()` generates C(n,k) paths correctly
- `walk_forward_cpcv()` trains XGBoost on each fold

**Gaps identified**:
1. **No strategy-matrix CSCV for PBO**: `probability_overfitting.py` has `calculate_pbo_from_matrix()` but the `_build_strategy_matrix()` in `research/pipeline.py` uses PROXY scaled returns (line 567: `scaled = [r * (trial_sharpe / mean_wr) for r in wr]`) instead of actually re-running each config on each window's OOS data
2. **No test-power analysis**: No check that CPCV paths have enough statistical power to detect overfitting
3. **Missing comparison with Walk-Forward Analysis**: The Deep et al. (2024) paper shows WFA (34 periods) vs CPCV — system lacks this comparative framework

**Severity**: MEDIUM — CPCV is implemented but the strategy matrix approximation introduces bias in PBO estimation.

**Implementation approach**:
- Fix `_build_strategy_matrix()` to actually re-run each sweep config on each WF window's OOS data
- Add power analysis helper function
- Add comparative WFA framework as per Deep et al. 2024

---

## GAP 3: Bootstrap CI for Max Drawdown — PARTIAL (MEDIUM)

**Current state**:
- `backtest/metrics.py`: `bootstrap_metric_ci()` uses stationary bootstrap for ANY metric (including max DD)
- `validation/bootstrap_sensitivity.py`: Uses i.i.d. bootstrap (WRONG for max DD — violates temporal structure)
- `core/monte_carlo.py`: Reports `ci_95_max_dd` from bootstrap simulation

**Gaps identified**:
1. **bootstrap_sensitivity.py uses i.i.d. bootstrap**: `rng.choice(values)` randomly resamples individual bars — destroys temporal autocorrelation and makes max DD CI unreliable
2. **No dedicated max DD CI function**: `bootstrap_metric_ci()` is generic but not called with max DD metric anywhere in the pipeline
3. **Monte Carlo simulator computes DD distribution** but doesn't provide proper CI for max DD

**Severity**: MEDIUM — Bootstrap CI for Sharpe is in the pipeline but max DD CI is not properly integrated.

**Implementation approach**:
- Add `bootstrap_max_drawdown_ci()` that uses `stationary_bootstrap()` (already exists)
- Integrate into `OverfittingDetector` as a new check
- Replace i.i.d. bootstrap in `bootstrap_sensitivity.py` with stationary bootstrap for max DD

---

## GAP 4: Regime-Switching Backtest — PARTIAL (HIGH)

**Current state**:
- `core/regime_filter.py`: Regime detection (TRENDING_UP/DOWN, RANGING, HIGH_VOL, LOW_VOL, CRISIS) with position multipliers
- `core/kelly.py`: `kelly_adjust_for_regime()` adjusts Kelly fraction by regime
- `backtest/engine.py`: Accepts `regime` parameter but engine passes `regime=None` (line 563)

**Gaps identified**:
1. **Backtest engine doesn't detect regime**: The engine receives regime=None from strategies, doesn't auto-detect it
2. **No regime-specific backtest paths**: Should test performance in each regime separately
3. **No regime transition cost**: When regime changes, should account for position adjustment costs
4. **Validation doesn't test regime robustness**: No check that strategy works across multiple regimes

**Severity**: HIGH — Without regime-aware backtesting, the system overestimates performance by assuming uniform market conditions. The stress test shows regime_shift causes -155% PnL and 631% DD.

**Implementation approach**:
- Add regime detection to backtest engine loop
- Generate regime-tagged equity curves
- Add regime-specific metrics (Sharpe per regime)
- Integrate into validation as regime robustness check

---

## GAP 5: Adverse Selection in Limit Orders — MISSING (HIGH)

**Current state**:
- `execution/fill_model.py`: Handles market orders only (BUY at ask, SELL at bid)
- `execution/execution_simulator.py`: Phase 3 added square-root market impact and adverse selection for MARKET orders
- `execution/tca_metrics.py`: Has `adverse_selection_bps` field
- `cost/forbidden_shortcuts.py`: Lists `"queue_position_without_depth"` as forbidden shortcut

**Gaps identified**:
1. **No limit order fill model**: System only supports market orders. Strategies like limit order book trading, TWAP, VWAP, iceberg orders can't be realistically simulated
2. **No queue position modeling**: When a limit order is placed, its position in the queue affects fill probability and adverse selection
3. **No fill probability model**: For limit orders, fill probability depends on distance from BBO, order book depth, volatility
4. **Adverse selection only estimated as fixed bps**: Should be dynamic based on order flow toxicity (VPIN/Kyle's lambda)

**Severity**: HIGH — For any strategy using limit orders (which most institutional strategies do), the current system either can't simulate them or uses unrealistic 100% fill assumptions.

**Implementation approach**:
- Add `execution/limit_order_model.py` with:
  - Fill probability model: P(fill) = f(distance_from_mid, volatility, order_book_depth)
  - Queue position model: expected wait time based on order book dynamics
  - Adverse selection premium: based on order flow toxicity
- Add `OrderType.LIMIT` to fill model
- Add partial fill simulation

---

## PRIORITY MATRIX

| Gap | Severity | Complexity | Implementation Effort |
|-----|----------|------------|----------------------|
| White's Reality Check / SPA | HIGH | MEDIUM | 2-3 days |
| CPCV Strategy Matrix Fix | MEDIUM | LOW | 1 day |
| Max DD Bootstrap CI | MEDIUM | LOW | 0.5 day |
| Regime-Switching Backtest | HIGH | MEDIUM | 2-3 days |
| Limit Order Adverse Selection | HIGH | HIGH | 5-7 days |

---

## REFERENCES

1. White, H. (2000). "A reality check for data snooping." Econometrica, 68(5), 1097-1126.
2. Hansen, P. R. (2005). "A test for superior predictive ability." Journal of Business & Economic Statistics, 23(4), 365-380.
3. Bailey, D. H., & Lopez de Prado, M. (2014). "The deflated Sharpe ratio." Journal of Risk, 16(3).
4. Bailey, D. H., & Lopez de Prado, M. (2015). "The probability of backtest overfitting." Journal of Computational Finance, 20(4).
5. Deep, G., Deep, A., & Lamptey, W. (2024). "Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals." arXiv:2512.12924.
6. Politis, D. N., & Romano, J. P. (1994). "The stationary bootstrap." Journal of the American Statistical Association, 89(428), 1303-1313.
