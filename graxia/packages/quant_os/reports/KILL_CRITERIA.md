# Pre-Committed Kill Criteria

## Strategy: Liquidity Sweep (XAUUSD)

### Stop Trading If:
1. **Net P&L after 200 OOS trades** is negative → STOP
2. **Win rate drops below 52%** (above random but below breakeven after costs) → STOP
3. **Max drawdown exceeds 3%** of account → HALT, review
4. **3 consecutive losing weeks** → PAUSE, investigate
5. **Feature importance stability**: if top feature sign flips across 3+ walk-forward folds → STOP (overfit)

### Pivot If:
1. **XAUUSD spread > 3 pips average** during trading session → pivot to EURUSD/GBPUSD
2. **Cost/move ratio > 60%** consistently → pivot to higher timeframe (15min)
3. **Model accuracy drops below 55% OOS** for 50+ consecutive trades → retrain or pivot feature set

### Review Cadence:
- Weekly: check win rate, P&L, drawdown
- Monthly: re-run walk-forward validation
- Quarterly: full adversarial stress test (label shuffling, cost perturbation)

### Decision Authority:
- HALT: automatic (risk limits) or manual (developer)
- RESUME: manual only (developer approval required)
- STOP: permanent (requires new hypothesis before resuming)
