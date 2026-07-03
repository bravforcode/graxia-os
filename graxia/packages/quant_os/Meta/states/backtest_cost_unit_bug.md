# Audit: backtest_cost.py Unit Mismatch (separate bug)

## Finding
`backtest_cost.py` expects `spread_cost`/`slippage_p90` in **dollars per 0.01 lot** (docstring + defaults: 0.17+0.39=$0.56), but `run_walk_forward.py` passes values from `cost_calibration.json` which are in **return units** (0.000147).

## Impact
- Not causing the +$10,789 illusion (that was walk_forward.py's missing *2350)
- But if backtest_cost.py is ever used for verdict input, it will use wrong cost magnitude
- Current Phase 5 backtest results show "0 trades (model mismatch)" — this feature was never operational

## Location
- `backtest_cost.py` line 99-100: docstring says "in dollars"
- `backtest_cost.py` line 119: `cost_per_trade = (spread_cost + slippage_p90) * lot_mult` — treats input as dollars
- `run_walk_forward.py` line 413-414: passes `spread_cost` and `slippage_p90` from cost_calibration.json (return units)

## Fix needed
Either:
1. Convert input from return units to dollars: `spread_cost * price` in `compute_trade_pnl`
2. Or change convention so all callers pass dollars

## Priority
Low — module was never producing valid output anyway (model mismatch). Fix when backtest_cost.py is operationalized.
