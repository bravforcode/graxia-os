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
| XAUUSD | 0.65 | 72.00 | Pepperstone Razor: $0 commission on metals. spread_bps_max reflects a real ~130bps rollover-window spread spike observed 2026-06-26T01:00 UTC (325 raw ticks >5bps in that window) — see stress_scenarios.XAUUSD_rollover_spike_20260626. Excluded from median/p95 central-tendency stats, included in min/max/std. |
| USDJPY | 7.25 | 7.37 | Pepperstone Razor: $7/rt commission on FX |
| OIL | 9.76 | 9.76 | Pepperstone CFD: $0 commission on energy. |

## Annual Cost Drag Calculation

Formula: `n_assets x rebalances_per_year x avg_turnover_per_rebalance x cost_bps x 2`

Assumptions:
- Assets: 8
- Rebalances per year: 52 (weekly)
- Each rebalance: weight_change × cost_bps / 10000

**Typical**: avg round-trip cost = 5.9 bps
**Stress**: avg round-trip cost = 29.7 bps

## Lookback = 20 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 353.47% |
| Annualized Return | 10.55% |
| Annualized Vol | 10.99% |
| Sharpe Ratio | 0.960 |
| Sortino Ratio | 1.270 |
| Max Drawdown | -24.98% |
| DD Duration | 1087 days |
| Win Rate | 51.5% |
| Profit Factor | 1.22 |
| Skewness | 0.538 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 26.5 |
| Annual Cost Drag (%) | 0.27% |
| Avg Weekly Turnover | 2.127 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.960 |
| Expected Max Sharpe (null) | 0.369 |
| Deflated Sharpe | 0.010 |
| P(alpha) | 0.0096 |
| Significant (95%) | YES |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 353.47% |
| Annualized Return | 10.55% |
| Annualized Vol | 10.99% |
| Sharpe Ratio | 0.960 |
| Sortino Ratio | 1.270 |
| Max Drawdown | -24.98% |
| DD Duration | 1087 days |
| Win Rate | 51.5% |
| Profit Factor | 1.22 |
| Skewness | 0.538 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 26.5 |
| Annual Cost Drag (%) | 0.27% |
| Avg Weekly Turnover | 2.127 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.960 |
| Expected Max Sharpe (null) | 0.369 |
| Deflated Sharpe | 0.010 |
| P(alpha) | 0.0096 |
| Significant (95%) | YES |

## Lookback = 40 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 274.98% |
| Annualized Return | 9.33% |
| Annualized Vol | 11.21% |
| Sharpe Ratio | 0.832 |
| Sortino Ratio | 1.093 |
| Max Drawdown | -20.84% |
| DD Duration | 837 days |
| Win Rate | 50.4% |
| Profit Factor | 1.18 |
| Skewness | 0.282 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 21.5 |
| Annual Cost Drag (%) | 0.22% |
| Avg Weekly Turnover | 1.657 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.832 |
| Expected Max Sharpe (null) | 0.372 |
| Deflated Sharpe | 0.036 |
| P(alpha) | 0.0356 |
| Significant (95%) | YES |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 274.98% |
| Annualized Return | 9.33% |
| Annualized Vol | 11.21% |
| Sharpe Ratio | 0.832 |
| Sortino Ratio | 1.093 |
| Max Drawdown | -20.84% |
| DD Duration | 837 days |
| Win Rate | 50.4% |
| Profit Factor | 1.18 |
| Skewness | 0.282 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 21.5 |
| Annual Cost Drag (%) | 0.22% |
| Avg Weekly Turnover | 1.657 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.832 |
| Expected Max Sharpe (null) | 0.372 |
| Deflated Sharpe | 0.036 |
| P(alpha) | 0.0356 |
| Significant (95%) | YES |

## Lookback = 60 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 200.62% |
| Annualized Return | 7.85% |
| Annualized Vol | 11.05% |
| Sharpe Ratio | 0.711 |
| Sortino Ratio | 0.888 |
| Max Drawdown | -26.04% |
| DD Duration | 1127 days |
| Win Rate | 51.1% |
| Profit Factor | 1.15 |
| Skewness | -0.071 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 17.1 |
| Annual Cost Drag (%) | 0.17% |
| Avg Weekly Turnover | 1.338 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.711 |
| Expected Max Sharpe (null) | 0.375 |
| Deflated Sharpe | 0.096 |
| P(alpha) | 0.0958 |
| Significant (95%) | NO |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 200.62% |
| Annualized Return | 7.85% |
| Annualized Vol | 11.05% |
| Sharpe Ratio | 0.711 |
| Sortino Ratio | 0.888 |
| Max Drawdown | -26.04% |
| DD Duration | 1127 days |
| Win Rate | 51.1% |
| Profit Factor | 1.15 |
| Skewness | -0.071 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 17.1 |
| Annual Cost Drag (%) | 0.17% |
| Avg Weekly Turnover | 1.338 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 0.711 |
| Expected Max Sharpe (null) | 0.375 |
| Deflated Sharpe | 0.096 |
| P(alpha) | 0.0958 |
| Significant (95%) | NO |

## Lookback = 120 days

### Typical

| Metric | Value |
|--------|-------|
| Total Return | 399.88% |
| Annualized Return | 11.13% |
| Annualized Vol | 10.37% |
| Sharpe Ratio | 1.073 |
| Sortino Ratio | 1.450 |
| Max Drawdown | -15.46% |
| DD Duration | 695 days |
| Win Rate | 49.9% |
| Profit Factor | 1.23 |
| Skewness | 0.299 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 13.0 |
| Annual Cost Drag (%) | 0.13% |
| Avg Weekly Turnover | 0.878 |

### DSR: Typical

| Metric | Value |
|--------|-------|
| Observed Sharpe | 1.073 |
| Expected Max Sharpe (null) | 0.371 |
| Deflated Sharpe | 0.003 |
| P(alpha) | 0.0029 |
| Significant (95%) | YES |

### Stress

| Metric | Value |
|--------|-------|
| Total Return | 399.88% |
| Annualized Return | 11.13% |
| Annualized Vol | 10.37% |
| Sharpe Ratio | 1.073 |
| Sortino Ratio | 1.450 |
| Max Drawdown | -15.46% |
| DD Duration | 695 days |
| Win Rate | 49.9% |
| Profit Factor | 1.23 |
| Skewness | 0.299 |
| Observation Days | 3830 |
| Observation Years | 15.2 |
| Annual Cost Drag (bps) | 13.0 |
| Annual Cost Drag (%) | 0.13% |
| Avg Weekly Turnover | 0.878 |

### DSR: Stress

| Metric | Value |
|--------|-------|
| Observed Sharpe | 1.073 |
| Expected Max Sharpe (null) | 0.371 |
| Deflated Sharpe | 0.003 |
| P(alpha) | 0.0029 |
| Significant (95%) | YES |

## Summary Comparison

| Lookback | Scenario | Sharpe | Ann Ret | Max DD | Cost Drag (bps) | DSR Sig |
|----------|----------|--------|---------|--------|-----------------|---------|
| 20 | Typical | 0.960 | 10.55% | -24.98% | 27 | YES |
| 20 | Stress | 0.960 | 10.55% | -24.98% | 27 | YES |
| 40 | Typical | 0.832 | 9.33% | -20.84% | 22 | YES |
| 40 | Stress | 0.832 | 9.33% | -20.84% | 22 | YES |
| 60 | Typical | 0.711 | 7.85% | -26.04% | 17 | NO |
| 60 | Stress | 0.711 | 7.85% | -26.04% | 17 | NO |
| 120 | Typical | 1.073 | 11.13% | -15.46% | 13 | YES |
| 120 | Stress | 1.073 | 11.13% | -15.46% | 13 | YES |

## Cost Threshold Analysis

What Sharpe ratio is needed to cover annual costs?

| Scenario | Avg RT Cost (bps) | Annual Cost at 52 rebal/yr | Min Sharpe to Cover |
|----------|-------------------|---------------------------|---------------------|
| Typical | 5.9 | 7.35% | 0.735 |
| Stress | 29.7 | 37.08% | 3.708 |

## Methodology Notes

- Costs applied per-asset using measured Pepperstone Razor spreads
- Typical = median measured round-trip; Stress = P95 (XAUUSD uses 72bps worst-case)
- DSR: Bailey & Lopez de Prado (2014), 8 trials (4 lookbacks × 2 signal types)
- Vol targeting: 10% annualized, capped at 1.0 (no leverage)
- Inverse-vol weighting across assets, 60-day rolling window
- Weekly rebalance (Friday close), cost = |Δweight| × cost_bps / 10000
