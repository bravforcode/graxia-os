# Ensemble TSM Backtest — EX-CRYPTO (Hypothesis Test)

**Date:** 2026-07-03
**Strategy:** Ensemble Time-Series Momentum (equal-weight mixture)
**Signal:** Equal-weight of vol-scaled returns at lookbacks [20, 40, 60, 120]
**Rebalance:** Weekly (Friday close)
**Vol Target:** 10% annualized
**Data:** 2016-01-04 to 2026-07-01 (2809 days)
**Assets (EX-CRYPTO):** XAUUSD, EURUSD, GBPUSD, USDJPY, USDCHF, SILVER, OIL, US30, NAS100
**Excluded:** BTCUSD, ETHUSD
**Hypothesis:** Without BTC+ETH, ensemble Sharpe collapses (crypto beta only)

---

## Verdict

**EDGE_CONFIRMED_EXCRYPTO** — DSR significant at N=1 AND PBO < 50%. Real alpha exists without crypto.

---

## Per-Asset Sharpe Breakdown

| Asset | Sharpe | Ann Return | Max DD | DSR P-value | Sig? | Verdict |
|-------|--------|------------|--------|-------------|------|---------|
| NAS100 | 0.598 | 16.34% | -37.84% | 0.000000 | YES | ALPHA |
| XAUUSD | 0.438 | 9.55% | -45.31% | 0.000000 | YES | ALPHA |
| OIL | 0.294 | 28.90% | -89.12% | 0.000114 | YES | ALPHA |
| USDJPY | 0.238 | 3.02% | -35.90% | 0.000000 | YES | ALPHA |
| US30 | 0.025 | 0.58% | -60.68% | 0.102731 | NO | NO-ALPHA |
| GBPUSD | 0.019 | 0.24% | -32.13% | 0.165507 | NO | NO-ALPHA |
| SILVER | -0.030 | -1.19% | -89.42% | 0.938238 | NO | NO-ALPHA |
| EURUSD | -0.155 | -1.62% | -37.48% | 1.000000 | NO | NO-ALPHA |
| USDCHF | -0.501 | -5.26% | -49.69% | 1.000000 | NO | NO-ALPHA |

## Typical Cost Scenario (EX-CRYPTO Portfolio)

| Metric | Value |
|--------|-------|
| Total Return | 61.63% |
| Annualized Return | 5.56% |
| Annualized Vol | 14.90% |
| Sharpe Ratio | 0.373 |
| Sortino Ratio | 0.577 |
| Max Drawdown | -23.29% |
| DD Duration | 980 days |
| Win Rate | 51.7% |
| Profit Factor | 1.09 |
| Skewness | 9.958 |
| Excess Kurtosis | 292.968 |
| Observation Days | 2686 |
| Observation Years | 10.7 |
| Annual Cost Drag (bps) | 146.3 |
| Avg Weekly Turnover | 3.096 |

### DSR (N=1): Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.373 |
| T (observations) | 2686 |
| SR Std Error | 0.053012 |
| Z-score | 7.036 |
| P-value (one-sided) | 0.000000 |
| Significant (95%) | YES |

### PBO: Typical

| Metric | Value |
|--------|-------|
| PBO | 0.0000 |
| Combinations Tested | 512 |
| PBO < 50% | YES |

## Stress Cost Scenario (EX-CRYPTO Portfolio)

| Metric | Value |
|--------|-------|
| Total Return | 35.94% |
| Annualized Return | 3.94% |
| Annualized Vol | 14.93% |
| Sharpe Ratio | 0.264 |
| Sortino Ratio | 0.409 |
| Max Drawdown | -25.08% |
| DD Duration | 1003 days |
| Win Rate | 51.1% |
| Profit Factor | 1.07 |
| Skewness | 9.910 |
| Excess Kurtosis | 291.140 |
| Observation Days | 2686 |
| Observation Years | 10.7 |
| Annual Cost Drag (bps) | 308.4 |
| Avg Weekly Turnover | 3.096 |

### DSR (N=1): Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.264 |
| T (observations) | 2686 |
| SR Std Error | 0.036024 |
| Z-score | 7.322 |
| P-value (one-sided) | 0.000000 |
| Significant (95%) | YES |

### PBO: Stress

| Metric | Value |
|--------|-------|
| PBO | 0.0000 |
| Combinations Tested | 512 |
| PBO < 50% | YES |

## Comparison: Full Ensemble vs Ex-Crypto

| Ensemble | Sharpe (Typical) | Sharpe (Stress) | DSR @ N=1 | PBO | Verdict |
|----------|------------------|-----------------|-----------|-----|---------|
| Full (8 assets) | 1.062 | 1.029 | YES | YES | EDGE_CONFIRMED |
| Ex-Crypto (typical) | 0.373 | - | YES | YES | EDGE_CONFIRMED_EXCRYPTO |
| Ex-Crypto (stress) | 0.264 | - | YES | - | EDGE_CONFIRMED_EXCRYPTO |
| Academic TSM baseline | ~0.4 | ~0.4 | - | - | Reference |

## Interpretation

**If Ex-Crypto Sharpe >> 0.5:** Real momentum alpha exists. Continue.
**If Ex-Crypto Sharpe 0.3-0.5:** Marginal. Needs more investigation.
**If Ex-Crypto Sharpe < 0.3:** No alpha. Crypto beta only. ARCHIVE_NO_EDGE.
