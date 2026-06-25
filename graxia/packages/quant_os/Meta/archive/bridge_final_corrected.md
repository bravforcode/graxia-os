# Bridge: Final Corrected State

## Session Verdict
**No config in this session has statistically significant edge.** Three independent methods agree (block bootstrap CI contains zero, iid bootstrap CI contains zero, parametric t-test p=0.58). Paper trading = NOT READY. EURUSD = CLOSED (negative gross after correct cost).

## Bug Fixes Applied
- `walk_forward.py:77`: `cost_per_dollars = (spread_cost + slippage_p90) * 2350.0`
- `backtest_cost.py:119`: `cost_per_trade = ... * price * lot_mult` (same unit bug)
- `tests/test_cost_unit_regression.py`: 6 tests asserting cost ∈ [$0.01, $5.00]/trade

## Anomaly: Fold Count 332→166
**Confirmed from raw JSON** (Select-String on file, not memory):
- v3_buggy: `step=100`
- v3_fixed: `step=200` (CLI default)
Both have `test_window=200`. The fold count halving is from step=100 vs 200, same as 497→332 in Finding #4 earlier. Cost fix had ZERO effect on fold/trade count.

**Correction**: Finding #4 in the earlier audit was wrong — I confused `test_window` (200, in filename) with `step`. v3 buggy was step=100, not step=200.

## XAUUSD Final Numbers (v3_fixed, step=200)

| Metric | Value | Significant? |
|--------|-------|-------------|
| Net | +$1,303.52 | — |
| t-test | t=0.55, p=0.58 | NO |
| Block bootstrap 95% CI | [−$22.44, +$34.78] | NO |
| IID bootstrap 95% CI | [−$20.07, +$34.96] | NO |
| P(mean > 0) | 71.4% | NO |
| Fold win rate | 60.8% | Misleading (heavy tails) |
| Kurtosis | 8.94 | Heavy tails |
| Skew | −0.84 | Negative |
| Accuracy × net_pnl correlation | r=0.656 | Strong |

## Worst Folds Analysis (Corrected)

**Confirmed**: Model accuracy drops to 0.17–0.46 during worst folds (vs mean ~0.59). Low accuracy drives losses, not spread/magnitude issues.

**Withdrawn claims**:
1. ~~"~40 fold periodicity"~~ — False. No periodic pattern. Low-accuracy folds (42/166 = 25.3%) are scattered throughout.
2. ~~"NY session dominates worst folds"~~ — Exaggerated with n=3. Bottom 20: NY 8 vs 7.2 expected by base rate. Session is NOT a reliable predictor.

**Confirmed**: 25.3% of folds have accuracy < 0.5 (worse than random). These are frequent enough to dominate risk. The tail risk (kurtosis=8.94) comes from accuracy-diving periods, not from magnitude outliers.

## Hypothesis (not confirmed): Regime Filter

The accuracy-driven pattern suggests that if there's an ex-ante signal predicting when the model's direction accuracy will degrade, a regime filter could reduce tail risk. This is **unconfirmed**:

1. ~~ForexFactory calendar ingested in Week 3~~ — **FALSE. No ForexFactory data exists on disk.** Cannot join.
2. ATR percentile during worst periods — not tested.
3. Any ex-ante signal for accuracy drops — **no evidence found.**
4. Tail risk currently has no known ex-ante predictor — may be structural limitation.

**Overlap detail**: 16/20 bottom-by-PnL folds overlap with accuracy<0.5. Remaining 4 folds (74, 129, 139, 146) lose money despite accuracy≥0.5 — these are R:R asymmetry losses (direction right but losing trades larger). Two distinct failure modes exist: accuracy failure (primary) and R:R failure (secondary).

**Without ForexFactory data or some other ex-ante signal, the regime filter hypothesis cannot be tested.** Do not implement.

## Paper Trading: NOT READY
No config in this session has statistically significant edge. Do not deploy.
