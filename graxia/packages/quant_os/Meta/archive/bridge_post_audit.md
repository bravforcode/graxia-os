# Bridge: Final Session State — Post Audit

## Cost Bug
**Fixed.** `scripts/walk_forward.py` line 77: `cost_per_dollars = (spread_cost + slippage_p90) * 2350.0`

## Regression Test
`tests/test_cost_unit_regression.py` — 6 tests, all passing. Asserts cost/trade is $0.01-$5.00 for any realistic spread+slippage. Prevents silent recurrence.

## Audit Results

| Finding | Status | Detail |
|---------|--------|--------|
| #1: Cost bug (missing *2350) | **FIXED** | cost was 0.0004x of correct; t=0.50 after fix |
| #2: Magnitude filter leakage | **PASS** | No leakage; both models predict out-of-sample |
| #3: Fold reduction 497→332 | **PASS** | Different step sizes (100→200) |
| #4: Threshold leakage | **PASS** | 0.0005 was pre-specified default, not tuned post-hoc |
| #5: backtest_cost.py unit mismatch | **DOCUMENTED** | Expects dollars, receives return units. Low priority |

## XAUUSD Rerun (Fixed Cost)
| Metric | Buggy (v3) | Fixed (v3_fixed) |
|--------|-----------|-----------------|
| Folds | 332 | 166 |
| Trades | 26,228 | 13,154 |
| Cost/trade | $0.000146 ❌ | **$0.3455 ✅** |
| Gross | $10,793.06 | $5,847.60 |
| Net | **+$10,789.25** | **+$1,303.52** |
| t-stat | 3.12 (✅ illusory) | **0.56 (❌ NOT significant)** |
| Positive folds | 64.1% | 60.8% |
| Kurtosis | — | **8.94** (heavy tails) |

## Key Insight: Heavy Tails (kurtosis=8.94)
- Top 3 worst folds (1.8%) account for 21.2% of total loss
- Worst single fold = -$953.89 (73% of total net profit)
- Max consecutive losing streak = 5 folds
- Negative skew (-0.84) explains why t=0.56 despite 60.8% positive folds
- **Fundamental vulnerability**: strategy has regime-dependent tail risk that magnitude filter doesn't eliminate

## EURUSD Status: CLOSED
Net after correct cost = **−$98.60** (t=-1.59). Negative gross + correct cost = no edge. No threshold tuning can fix this.

## Paper Trading: NOT READY
No config has statistically significant edge after cost fix. XAUUSD has positive gross but t=0.56 and kurtosis=8.94. Do not deploy.

## Next
1. Holdout validation only IF a subsequent improvement achieves t>2.0 with kurtosis <5
2. Fix backtest_cost.py if operationalized
3. Revisit only with fundamentally different strategy design that addresses tail risk
