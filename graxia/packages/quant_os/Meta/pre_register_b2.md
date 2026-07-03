# Pre-Registration: B2 Stop-Loss Paper Trade

**Created**: 2026-06-25
**Purpose**: Pre-register evaluation criteria BEFORE any prospective data is seen.
**Rule**: No config/threshold changes during paper trade period. Violation voids the entire test.

## Configuration (locked)
- Symbol: XAUUSD
- Timeframe: 15min
- Strategy: Existing XGBoost classifier + magnitude filter (unchanged)
- **Single change**: Hard stop-loss at $6.30 per trade (1× avg_win)
- Stop type: Market stop-loss (execution subject to slippage/gap risk)
- All other params unchanged (train_window=500, test_window=200, step=200, conf≥0.85, expected_profit>0.0005, cost=0.000147 return units)

## Pass Criteria (locked)
1. **avg_net/trade ≥ $0.40** (after actual costs, including stop slippage)
2. **Win rate (net PnL > 0) ≥ 0.55**
3. **t-stat ≥ 2.0** on block bootstrap 95% CI (prospective data only)

All three must pass for "PASS" verdict. If any fails, the configuration fails.

## Evaluation Period
- Start: [TBD — trading machine setup + broker switch]
- Duration: 28 calendar days (4 weeks) of continuous paper trading
- Data: Purely prospective (no historical backtest/overlap)
- Evaluation at end of 28 days only — no mid-period peeking

## Pre-registered Contingency
If fail avg_net but pass WR:
  → Gap risk exceeded estimate. Next attempt: stop at $7.00, repeat 4-week paper trade.
If fail WR:
  → Accuracy-failure is structural. Requires feature redesign (cross-asset + session model).
  → B2 alone insufficient — no further tuning on same strategy.

## Signatories
- **Pre-registered by**: bridge agent
- **Date**: 2026-06-25
- **Review date**: 2026-07-23 (28 days)

## Violations That Void This Test
- Adjusting $6.30 stop threshold during paper trade
- Evaluating PnL before 28-day mark and making decisions based on it
- Adding any additional filter/exit/modification during the period
- Running parallel historical tests that could influence paper trade decisions
