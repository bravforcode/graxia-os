# TSM Momentum Backtest — Real Measured Costs (Pepperstone Razor)

**Date:** 2026-07-03
**Strategy:** Academic Time-Series Momentum (TSM)
**Signal:** sign(lookback_return) × vol_target / realized_vol
**Rebalance:** Weekly (Friday close)
**Vol Target:** 10% annualized
**Data:** 2006-06-13 to 2026-06-29 (7320 days)
**Assets:** XAUUSD, EURUSD_YF, GBPUSD_YF, USDJPY, BTC_YF, ETH_YF, SILVER, OIL

---

## Verdict

**ARCHIVE_NO_EDGE** — DSR not significant even at typical costs. TSM momentum has no edge after real costs.

---

## Per-Asset Cost Breakdown (Round-Trip bps)

| Asset | Typical (median) | Stress (P95/worst) | Source |
|-------|------------------|--------------------|--------|
| XAUUSD | 0.72 | 72.00 | Pepperstone Razor: $0 commission on metals |
| EURUSD | 7.00 | 7.00 | Pepperstone Razor: $7/rt commission on FX |
| GBPUSD | 7.30 | 7.60 | Pepperstone Razor: $7/rt commission on FX |
| USDJPY | 7.12 | 7.38 | Pepperstone Razor: $7/rt commission on FX |
| BTCUSD | 4.86 | 5.16 | Pepperstone CFD: $0 commission on crypto |
| ETHUSD | 23.34 | 23.54 | Pepperstone CFD: $0 commission on crypto |
| SILVER | 13.16 | 14.44 | Pepperstone Razor: $0 commission on metals (SILVER) |
| OIL | 9.76 | 9.76 | Pepperstone CFD: $0 commission on energy (OIL/WTI) |

## Annual Cost Drag Calculation

Formula: `n_assets x rebalances_per_year x avg_turnover_per_rebalance x cost_bps x 2`

Assumptions:
- Assets: 8
- Rebalances per year: 52 (weekly)
- Each rebalance: weight_change × cost_bps / 10000

**Typical**: avg round-trip cost = 9.2 bps
**Stress**: avg round-trip cost = 18.4 bps

## Lookback = 20 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 332.08% |
| Annualized Return | 10.23% |
| Annualized Vol | 11.00% |
| Sharpe Ratio | 0.931 |
| Sortino Ratio | 1.232 |
| Max Drawdown | -25.83% |
| DD Duration | 1447 days |
| Win Rate | 51.3% |
| Profit Factor | 1.21 |
| Skewness | 0.536 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 58.4 |
| Annual Cost Drag (%) | 0.58% |
| Avg Weekly Turnover | 2.127 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.931 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.529 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 331.15% |
| Annualized Return | 10.22% |
| Annualized Vol | 11.00% |
| Sharpe Ratio | 0.929 |
| Sortino Ratio | 1.230 |
| Max Drawdown | -25.86% |
| DD Duration | 1447 days |
| Win Rate | 51.3% |
| Profit Factor | 1.21 |
| Skewness | 0.536 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 59.8 |
| Annual Cost Drag (%) | 0.60% |
| Avg Weekly Turnover | 2.127 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.929 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.530 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

## Lookback = 40 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 261.75% |
| Annualized Return | 9.09% |
| Annualized Vol | 11.22% |
| Sharpe Ratio | 0.810 |
| Sortino Ratio | 1.066 |
| Max Drawdown | -21.17% |
| DD Duration | 837 days |
| Win Rate | 50.3% |
| Profit Factor | 1.18 |
| Skewness | 0.281 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 45.0 |
| Annual Cost Drag (%) | 0.45% |
| Avg Weekly Turnover | 1.657 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.810 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.649 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 261.11% |
| Annualized Return | 9.08% |
| Annualized Vol | 11.22% |
| Sharpe Ratio | 0.809 |
| Sortino Ratio | 1.065 |
| Max Drawdown | -21.18% |
| DD Duration | 837 days |
| Win Rate | 50.3% |
| Profit Factor | 1.18 |
| Skewness | 0.281 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 46.1 |
| Annual Cost Drag (%) | 0.46% |
| Avg Weekly Turnover | 1.657 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.809 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.650 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

## Lookback = 60 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 190.73% |
| Annualized Return | 7.63% |
| Annualized Vol | 11.05% |
| Sharpe Ratio | 0.691 |
| Sortino Ratio | 0.863 |
| Max Drawdown | -26.64% |
| DD Duration | 1445 days |
| Win Rate | 51.0% |
| Profit Factor | 1.15 |
| Skewness | -0.072 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 38.8 |
| Annual Cost Drag (%) | 0.39% |
| Avg Weekly Turnover | 1.338 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.691 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.769 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 190.33% |
| Annualized Return | 7.62% |
| Annualized Vol | 11.05% |
| Sharpe Ratio | 0.690 |
| Sortino Ratio | 0.862 |
| Max Drawdown | -26.66% |
| DD Duration | 1445 days |
| Win Rate | 51.0% |
| Profit Factor | 1.15 |
| Skewness | -0.072 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 39.7 |
| Annual Cost Drag (%) | 0.40% |
| Avg Weekly Turnover | 1.338 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.690 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.770 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

## Lookback = 120 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 389.44% |
| Annualized Return | 10.99% |
| Annualized Vol | 10.37% |
| Sharpe Ratio | 1.059 |
| Sortino Ratio | 1.433 |
| Max Drawdown | -15.54% |
| DD Duration | 695 days |
| Win Rate | 49.9% |
| Profit Factor | 1.23 |
| Skewness | 0.299 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 27.0 |
| Annual Cost Drag (%) | 0.27% |
| Avg Weekly Turnover | 0.878 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 1.059 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.400 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 388.92% |
| Annualized Return | 10.98% |
| Annualized Vol | 10.37% |
| Sharpe Ratio | 1.059 |
| Sortino Ratio | 1.432 |
| Max Drawdown | -15.54% |
| DD Duration | 812 days |
| Win Rate | 49.9% |
| Profit Factor | 1.23 |
| Skewness | 0.299 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 27.7 |
| Annual Cost Drag (%) | 0.28% |
| Avg Weekly Turnover | 0.878 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 1.059 |
| Expected Max Sharpe (null) | 1.459 |
| Deflated Sharpe | -0.401 |
| P(alpha) | 1.0000 |
| Significant (95%) | NO |

## Summary Comparison

| Lookback | Scenario | Sharpe | Ann Ret | Max DD | Cost Drag (bps) | DSR Sig |
|----------|----------|--------|---------|--------|-----------------|---------|
| 20 | Typical | 0.931 | 10.23% | -25.83% | 58 | NO |
| 20 | Stress | 0.929 | 10.22% | -25.86% | 60 | NO |
| 40 | Typical | 0.810 | 9.09% | -21.17% | 45 | NO |
| 40 | Stress | 0.809 | 9.08% | -21.18% | 46 | NO |
| 60 | Typical | 0.691 | 7.63% | -26.64% | 39 | NO |
| 60 | Stress | 0.690 | 7.62% | -26.66% | 40 | NO |
| 120 | Typical | 1.059 | 10.99% | -15.54% | 27 | NO |
| 120 | Stress | 1.059 | 10.98% | -15.54% | 28 | NO |

## Cost Threshold Analysis

What Sharpe ratio is needed to cover annual costs?

| Scenario | Avg RT Cost (bps) | Annual Cost at 52 rebal/yr | Min Sharpe to Cover |
|----------|-------------------|---------------------------|---------------------|
| Typical | 9.2 | 11.43% | 1.143 |
| Stress | 18.4 | 22.91% | 2.291 |

## Methodology Notes

- Costs applied per-asset using measured Pepperstone Razor spreads
- Typical = median measured round-trip; Stress = P95 (XAUUSD uses 72bps worst-case)
- DSR: Bailey & Lopez de Prado (2014), 8 trials (4 lookbacks × 2 signal types)
- Vol targeting: 10% annualized, capped at 1.0 (no leverage)
- Inverse-vol weighting across assets, 60-day rolling window
- Weekly rebalance (Friday close), cost = |Δweight| × cost_bps / 10000
