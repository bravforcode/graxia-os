# Bridge: Post-Audit State — Cleanup Complete

## Session Verdict
**No config in this session has statistically significant edge.** Every "breakthrough" number this session was a unit bug or noise.

## Bug Fixes Applied (all three code paths)

| File | What | Status |
|------|------|--------|
| `walk_forward.py:77` | `cost_per_dollars = (spread_cost + slippage_p90) * 2350.0` | **FIXED** |
| `backtest_cost.py:119` | `cost_per_trade = ... * price * lot_mult` | **FIXED** |
| `tests/test_cost_unit_regression.py` | 6 tests asserting cost/trade ∈ [$0.01, $5.00] | **ADDED** (all PASS) |
| `Meta/states/backtest_cost_unit_bug.md` | Documented the backtest_cost.py unit mismatch | **DOCUMENTED** |

## Anomaly Resolution

**"Why 332→166 folds from cost fix?"** — Buggy v3 ran with step=100, fixed ran with step=200. Same as previous 497→332 (step=100→200). NOT from cost fix.

**"Does magnitude filter use cost_per?"** — No. `expected_profit = direction * mag_pred * conf` (line 169). Zero cost involvement. The filter is cost-agnostic.

**"166 = total or filtered?"** — Total. All 166 folds have ≥1 trade. No selection bias.

## XAUUSD Final Numbers (v3_fixed, step=200, cost fixed)

| Metric | Value | Significant? |
|--------|-------|-------------|
| Net | +$1,303.52 | — |
| t-test | t=0.55, p=0.58 | NO |
| Block bootstrap 95% CI | [−$22.44, +$34.78] | NO (CI spans zero) |
| IID bootstrap 95% CI | [−$20.07, +$34.96] | NO (CI spans zero) |
| P(mean > 0) | 71.4% | NO (need ≥95%) |
| Fold win rate | 60.8% | misleading (heavy tails) |
| Skew | −0.84 | negative |
| Kurtosis | 8.94 | heavy tails |

**Interpretation**: Gross edge exists (~$5,848 gross on 13,154 trades) but cost ($4,544) erodes most of it. Remaining $1,304 net is within noise range for this distribution's variance. Kurtosis=8.94 means occasional -$500 to -$950 losing folds dominate the risk.

## EURUSD: CLOSED
Net after correct cost = −$98.60 (gross +$103.64 − cost $202.24). Negative edge. No threshold tuning can salvage this.

## Paper Trading: NOT READY (Confirmed by 3 independent tests)
Block bootstrap, iid bootstrap, and parametric t-test all agree: mean NOT significant.

## Relevant Files
- `scripts/walk_forward.py` — compute_fold_pnl fixed (cost_per_dollars = cost_per_return * 2350)
- `scripts/backtest_cost.py` — compute_trade_pnl fixed (same pattern, *price multiplier)
- `tests/test_cost_unit_regression.py` — 6 regression tests asserting $0.01-$5.00/trade
- `artifacts/walk_forward_v3_fixed/wf_XAUUSD_15min_500w_200t_conf0.85.json` — fresh run with correct cost
- `Meta/states/backtest_cost_unit_bug.md` — documentation of backtest_cost.py convention fix
