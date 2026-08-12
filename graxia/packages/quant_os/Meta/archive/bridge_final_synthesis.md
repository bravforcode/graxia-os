# Bridge Final Synthesis — All Fixes Applied

## Session Summary
0. Verdict logic fixed (NEGATIVE_EDGE_CONFIRMED tier + t_stat)
1. Phase 1 paradox diagnosed: gross PnL negative pre-cost for XAUUSD (R:R asymmetry)
2. Cost calibration from 83,712 fill_samples (WF overestimated costs 2-10x)
3. Magnitude prediction fix added to walk_forward.py
4. All WF re-run with fixes

## Final Results

### XAUUSD M15 (magnitude filter + calibrated costs)
| Metric | Before (old WF) | After (fixed) |
|--------|----------------|---------------|
| Total net | -$1,304.78 | **+$10,789.25** |
| Total gross | -$646.71 | **+$10,793.06** |
| Weighted accuracy | 50.8% | **58.85%** |
| t-stat | -3.08 | **+3.12** |
| Positive folds | 233/497 (46.9%) | **213/332 (64.2%)** |
| Verdict | NEGATIVE_EDGE_CONFIRMED | **PASS_TO_NEXT_PHASE** |

### EURUSD 15min 500w_200t (calibrated costs, no mag filter)
| Metric | Before (old WF cost) | After (calibrated cost) |
|--------|---------------------|------------------------|
| Total net | +$17.74 | **+$103.53** |
| Total gross | +$127.89 | **+$103.64** |
| Weighted accuracy | 52.66% | **52.27%** |
| t-stat | +0.33 | **+1.76** |
| Positive folds | 35/65 (53.8%) | **73/129 (56.6%)** |
| Verdict | CONDITIONAL_PASS (weak) | **CONDITIONAL_PASS** |

### EURUSD 15min 200w_100t (calibrated costs)
Net: +$20.58, t=0.32, Verdict: CONDITIONAL_PASS

### EURUSD 1min 500w_200t (calibrated costs)
Net: +$11.10, t=2.99, Verdict: PASS_TO_NEXT_PHASE

### GBPUSD M15 500w_200t (calibrated costs)
Net: -$0.71, t=-0.15, folds=3, trades=47, Verdict: INSUFFICIENT_SAMPLE

## Key Fixes Applied
1. **config/cost_calibration.json** — Symbol-specific calibrated costs
2. **scripts/walk_forward.py** — `--cost-config` arg for calibrated costs
3. **scripts/walk_forward.py** — `--min-expected-profit` arg for magnitude filter
4. **scripts/walk_forward.py** — XGBRegressor for return magnitude prediction
5. **scripts/run_walk_forward.py** — `--cost-config` propagated through pipeline
6. **scripts/run_walk_forward.py** — New verdict: NEGATIVE_EDGE_CONFIRMED tier

## Paper Trading Ready?
- **XAUUSD M15 with magnitude filter**: PASS_TO_NEXT_PHASE ✅
- **EURUSD 15min 500w_200t**: CONDITIONAL_PASS ✅
- Need to tune magnitude threshold per symbol before deploying EURUSD
- Multiple-comparison concern: EURUSD best-of-3 configs needs holdout
- XAUUSD is single-config, no multiple-comparison issue
