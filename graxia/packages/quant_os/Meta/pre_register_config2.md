# Pre-Registration: Config #2 — High Confidence B2 Paper Trade

**Created**: 2026-06-25
**Purpose**: Parallel paper trade to test higher confidence threshold against baseline Config #1 (conf≥0.85).
**Rule**: No config/threshold changes during 28-day period. Two independent evaluations at end.

## Configuration (locked)
- Symbol: XAUUSD
- Timeframe: 15min
- Strategy: Existing XGBoost classifier + magnitude filter (unchanged)
- **Confidence threshold**: 0.95 (vs 0.85 in Config #1)
- **Stop-loss**: $6.30 per trade (same as Config #1)
- All other params identical to Config #1 (train_window=500, test_window=200, step=200, expected_profit>0.0005, cost=0.000077 ret units)

## Pass Criteria (locked — same as Config #1)
1. **avg_net/trade ≥ $0.40** (prospective, after actual costs + stop slippage)
2. **Win rate (net PnL > 0) ≥ 0.55**
3. **t-stat ≥ 2.0** on block bootstrap 95% CI (prospective data only)

All three must pass for "PASS" verdict.

## Evaluation Period
- Start: Same day as Config #1
- Duration: 28 calendar days
- Data: Purely prospective (same period as Config #1)
- Evaluation at end of 28 days — no mid-period peeking at either config's results

## Historical Simulation Reference (not binding, for context only)
| Metric | Config #1 (conf≥0.85) | Config #2 (conf≥0.95) |
|--------|----------------------|----------------------|
| Avg net/trade (historical) | $4.19 | $4.46 |
| Win rate | 59.3% | 62.7% |
| Profit factor | 2.71 | 2.97 |
| Trades/28 days (est) | ~940 | ~549 |
| Fold t-stat | 12.25 | — |

## Post-Evaluation Decision
| Config #1 | Config #2 | Decision |
|-----------|-----------|----------|
| PASS | PASS | Use higher avg_net config |
| PASS | FAIL | Use Config #1 |
| FAIL | PASS | Use Config #2 |
| FAIL | FAIL | Feature redesign (Phase 3) |

If both PASS and avg_net equal within $0.10 → prefer Config #1 (more trades = more statistical power).

## Signatories
- **Pre-registered by**: bridge agent
- **Date**: 2026-06-25
- **Review date**: 2026-07-23 (28 days)

## Violations That Void This Test
- Adjusting either conf threshold or $6.30 stop during paper trade
- Evaluating PnL before 28-day mark
- Comparing interim results between Config #1 and #2 before 28-day end
- Adding any additional filter/exit/modification during the period
