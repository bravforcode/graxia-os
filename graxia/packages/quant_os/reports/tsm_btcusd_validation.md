# BTCUSD TSM Validation Report

**Date:** 2026-07-05
**Strategy:** Ensemble TSM (equal-weight mixture of lookbacks [20, 40, 60, 120])
**Asset:** BTCUSD (via yfinance BTC-USD daily data)
**Data:** 2016-01-01 to 2026-06-25 (3829 bars)
**BTC Costs:** RT=8.74bps, Swap Long=-3.0 bps/day, Swap Short=-1.5 bps/day

---

## Verdict

**GO** — OOS Sharpe = 0.564 > 0.5. BTCUSD shows real alpha. RECOMMENDED for inclusion.

**Recommended Weight: 15%** of multi-asset TSM portfolio

---

### Solo BTCUSD TSM (with swap)

| Metric | Value |
|--------|-------|
| Total Return | 11663.30% |
| Annualized Return | 52.38% |
| Annualized Vol | 63.26% |
| Sharpe Ratio | 0.828 |
| Sortino Ratio | 1.081 |
| Max Drawdown | -79.29% |
| DD Duration | 1899 days |
| Win Rate | 51.0% |
| Profit Factor | 1.19 |
| Skewness | 0.443 |
| Excess Kurtosis | 9.171 |
| Observation Days | 3702 |
| Observation Years | 14.7 |
| Annual Cost Drag (bps) | 745.9 |
| Annual Cost Drag (%) | 7.46% |
| Avg Weekly Turnover | 0.286 |
| Est. Total Trades | 78 |
| Avg Trade Duration | 7.0 days |

### DSR (N=1): Solo BTC

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.828 |
| T (observations) | 3702 |
| SR Std Error | 0.026236 |
| Z-score | 31.559 |
| P-value (one-sided) | 0.000000 |
| Significant (95%) | YES |

### 5-Asset Equal Weight

| Metric | Value |
|--------|-------|
| Total Return | 1594.73% |
| Annualized Return | 31.90% |
| Annualized Vol | 32.09% |
| Sharpe Ratio | 0.994 |
| Sortino Ratio | 1.704 |
| Max Drawdown | -29.29% |
| DD Duration | 861 days |
| Win Rate | 54.0% |
| Profit Factor | 1.27 |
| Skewness | 11.702 |
| Excess Kurtosis | 347.640 |
| Observation Days | 2612 |
| Observation Years | 10.4 |
| Annual Cost Drag (bps) | 313.5 |
| Annual Cost Drag (%) | 3.14% |
| Avg Weekly Turnover | 1.128 |
| Est. Total Trades | 295 |
| Avg Trade Duration | 7.0 days |

### DSR (N=1): 5-Asset Equal Weight

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.994 |
| T (observations) | 2612 |
| SR Std Error | 0.170331 |
| Z-score | 5.836 |
| P-value (one-sided) | 0.000000 |
| Significant (95%) | YES |


## Walk-Forward: BTC Solo (70/30)

| Period | Sharpe | Ann Ret | Max DD | Days |
|--------|--------|---------|--------|------|
| Train | 0.977 | 67.99% | -79.29% | 2680 |
| Test (OOS) | 0.564 | 27.02% | -54.92% | 1149 |


## Walk-Forward: 5-Asset Portfolio (70/30)

| Period | Sharpe | Ann Ret | Max DD | Days |
|--------|--------|---------|--------|------|
| Train | 1.049 | 38.66% | -28.59% | 1792 |
| Test (OOS) | 1.159 | 21.53% | -15.11% | 697 |


## BTC Weight Sensitivity

| BTC Weight | Sharpe | Sortino | Ann Ret | Max DD | Win Rate | Profit Factor | DSR P-value | Sig? |
|------------|--------|---------|---------|--------|----------|---------------|-------------|------|
| 0% | 0.643 | 0.783 | 11.12% | -12.64% | 53.7% | 1.13 | 0.000000 | YES |
| 5% | 0.693 | 0.858 | 11.48% | -11.17% | 53.3% | 1.14 | 0.000000 | YES |
| 8% | 0.716 | 0.904 | 11.70% | -10.29% | 53.5% | 1.14 | 0.000000 | YES |
| 10% | 0.728 | 0.935 | 11.84% | -9.90% | 52.9% | 1.14 | 0.000000 | YES |
| 15% | 0.743 | 1.003 | 12.21% | -10.56% | 51.7% | 1.14 | 0.000000 | YES |
| 20% | 0.739 | 1.042 | 12.57% | -11.23% | 50.6% | 1.14 | 0.000000 | YES |


## Correlation Analysis

### Return Correlation Matrix

```
          NAS100    XAUUSD       OIL    USDJPY       BTC
NAS100  1.000000  0.174041 -0.006587  0.017985  0.376847
XAUUSD  0.174041  1.000000  0.037725  0.009114  0.161457
OIL    -0.006587  0.037725  1.000000  0.022371 -0.029860
USDJPY  0.017985  0.009114  0.022371  1.000000  0.031450
BTC     0.376847  0.161457 -0.029860  0.031450  1.000000
```

- **Nominal bets:** 5
- **Avg pairwise correlation:** 0.0795
- **Effective bets:** 3.79
- **Diversification ratio:** 75.88%


### BTC Correlations

- BTC-NAS100: 0.3768
- BTC-XAUUSD: 0.1615
- BTC-OIL: -0.0299
- BTC-USDJPY: 0.0315


## Swap Cost Impact

| Metric | No Swap | With Swap | Drag |
|--------|---------|-----------|------|
| Sharpe | 0.931 | 0.828 | 0.103 |
| Ann Return | 58.90% | 52.38% | 6.53% |
| Max DD | -78.53% | -79.29% | |
| Annual Cost Drag | 93.3 bps | 745.9 bps | |

## Portfolio Comparison

| Portfolio | Sharpe | Ann Ret | Max DD | OOS Sharpe | DSR Sig? | Verdict |
|-----------|--------|---------|--------|------------|----------|---------|
| 4-Asset Baseline (no BTC) | 0.543 | 18.16% | -30.81% | — | YES | Baseline |
| 5-Asset Equal Weight (20% BTC) | 0.994 | 31.90% | -29.29% | 1.159 | YES | GO |
| BTCUSD Solo | 0.828 | 52.38% | -79.29% | 0.564 | YES | INCLUDE |
| Academic TSM baseline | ~0.4 | ~8% | -20% | — | — | Reference |

## Decision Criteria

| OOS Sharpe | Verdict | Action |
|------------|---------|--------|
| > 0.5 | GO | Include in portfolio at recommended weight |
| 0.3 - 0.5 | CONDITIONAL_GO | Include at small weight (5%), monitor closely |
| 0.0 - 0.3 | NO_GO | Do not include |
| < 0.0 | NO_GO | No alpha |

**Result: GO** (OOS Sharpe = 0.564)

---

## Methodology

- Signal: Equal-weight mixture of vol-scaled returns at lookbacks [20, 40, 60, 120]
- Vol targeting: 10% annualized, 60-day window, position capped at 1.5x
- Weekly rebalance (Friday close)
- Walk-forward: 70% train, 30% test
- BTC costs: 8.74 bps round-trip, -3.0 bps/day long swap, -1.5 bps/day short swap
- 4-asset costs: per-asset measured Pepperstone Razor spreads
- Weight sensitivity tested: 0%, 5%, 8%, 10%, 15%, 20%
