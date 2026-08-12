# ADR-002: Kelly Criterion Position Sizing

## Status
Accepted — Phase A (Week 1-2)

## Context
Graxia has `FixedFractionalSizer` (1% risk) but no mathematically optimal sizing method. The kvrancic repo demonstrated Kelly Criterion for adaptive position sizing based on actual win rate and payoff ratio.

## Decision
Enhance existing `risk/position_sizer.py` with:
1. Standalone `kelly_fraction()` function for reuse outside the sizer class
2. `TradeStatsTracker` for automatic rolling-window performance tracking
3. Guardrails: quarter-Kelly default (fraction=0.25), capped by golden rule max risk

## Consequences
+ Position size adapts to actual strategy performance
+ Standalone function can be used by backtest engine, risk engine, or strategy
+ Quarter-Kelly reduces variance vs full Kelly
- Requires historical trade data (TradeStatsTracker bootstraps from 0.5 win rate)
- Negative edge → Kelly returns 0 (no trade), which is correct behavior

## Mathematical Basis
```
f* = (b·p - q) / b
where b = avg_win/avg_loss, p = win_rate, q = 1-p
```
Quarter-Kelly (f* × 0.25) reduces growth rate by ~44% but reduces drawdown variance by ~94%.

## References
- kelly_fraction: "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market" (Thorp)
- kvrancic/algorithmic-trading-bot risk_management module
