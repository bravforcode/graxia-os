# Thaifxbook Data Validation — Phase 0 (pre-scale gate)

- **Date**: 2026-08-06
- **Account**: PutDejudomTraderUltimateHeadShot1 (`ff65308c-aeda-4cc9-ac85-ce469e98dbaa`)
- **Broker**: Exness · USD 1:2000 · verified=True
- **Source**: https://thaifxbook.com/p/ff65308c-aeda-4cc9-ac85-ce469e98dbaa
- **Fixture**: `market_data/thaifxbook/fixtures/putdejudom_ff65308c.json` (29 raw closed trades)

## Method

Recomputed standard metrics from the 29 raw closed trades with canonical
formulas (MetaStats spec: win rate, profit factor, expected payoff, avg win,
gain% on deposits, close-to-close max drawdown) and compared to the
platform-displayed numbers. Tolerance is relative (0.001 = 0.1%).

## Results

| Metric | Ours | Platform | Status |
|---|---|---|---|
| total_trades | 29.00  | 29.00  | **PASS** |
| win_rate_pct | 96.55 % | 96.55 % | **PASS** |
| net_profit_usd | 1132.92  | 1132.92  | **PASS** |
| profit_factor | 709.07  | 709.07  | **PASS** |
| expected_payoff | 39.07  | 39.07  | **PASS** |
| avg_win_usd | 40.52  | 40.52  | **PASS** |
| gain_pct | 380.01 % | 380.01 % | **PASS** |
| max_drawdown_pct* | 0.11 % | 0.11 % | **PASS** |

\* close-to-close approximation; platform may use intra-trade equity drawdown.

## Raw sanity cross-checks

- Today (4 trades) = 16.62 — platform shows 16.62
- Gross profit = 1134.52, gross loss = 1.60
- Wins 28/29 = 96.55% — platform shows 96.55%
- PF derivation: (1134.52 + 1.60) / 1.60 = 709.07 — platform shows 709.07
- Gain derivation: 1132.92 / 298.13 = 380.01% — platform shows 380.01%
- Final balance (close-to-close) = 1431.05 — platform shows 1431.05

## Verdict

**PASS** if all rows PASS above.

Platform-displayed metrics match canonical recomputation on this sample (PutDejudomTraderUltimateHeadShot1).
