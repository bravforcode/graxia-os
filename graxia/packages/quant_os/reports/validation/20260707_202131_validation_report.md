# Validation Report — 20260707_202131

## Summary
- **Assets:** XAUUSD, EURUSD
- **Total Time:** 19.7s
- **Overall Verdict:** ❌ **FAIL**
- **Gates:** 3/9 PASS

## Gate Results

| Gate | Status | Metric | Threshold | Details |
|------|--------|--------|-----------|---------|
| wfa_oos_positive | ❌ FAIL | 0.6667 | 0.7000 | 66.7% OOS windows positive |
| wfa_wfe | ❌ FAIL | -0.7307 | 0.5000 | WFE=-0.7307 |
| wfa_degradation | ✅ PASS | 0.0997 | 0.3000 | Degradation=10.0% |
| mc_ruin_prob | ❌ FAIL | 0.3440 | 0.0500 | P(Ruin)=34.40% |
| mc_drawdown_p95 | ⚠️ WARN | 0.2764 | 0.2500 | 95th percentile DD=27.6% |
| deflated_sharpe | ❌ FAIL | -2.1933 | 0.0000 | DSR=-2.1933 |
| pbo_overfitting | ❌ FAIL | 0.5000 | 0.5000 | PBO=0.5000 |
| stress_test | ✅ PASS | 0.9722 | 0.8000 | 97.2% scenarios positive |
| bootstrap_sharpe_ci | ✅ PASS | 0.0002 | 0.0000 | Sharpe CI lower=0.0002 |

## WFA

- **Status:** ✅ Complete (0.0s)
- **oos_consistency:** 0.6667
- **walk_forward_efficiency:** -0.7307
- **overfitting_score:** 0.0997
- **avg_is_sharpe:** 0.2774
- **avg_oos_sharpe:** 0.2497
- **n_windows:** 12

### Walk-Forward Windows

| Window | Symbol | IS Sharpe | OOS Sharpe | WFE |
|--------|--------|-----------|------------|-----|
| 0 | XAUUSD | 0.1250 | 0.3064 | 2.4510 |
| 1 | XAUUSD | 0.5781 | 1.0793 | 1.8670 |
| 2 | XAUUSD | 0.3524 | 0.5041 | 1.4305 |
| 3 | XAUUSD | -0.1816 | 1.3916 | -7.6631 |
| 4 | XAUUSD | 1.0249 | 0.6967 | 0.6798 |
| 5 | XAUUSD | 1.6121 | -0.1873 | -0.1162 |
| 0 | EURUSD | 0.2445 | -1.2176 | -4.9797 |
| 1 | EURUSD | 0.2089 | 0.6015 | 2.8801 |
| 2 | EURUSD | -1.0794 | 0.3057 | -0.2832 |
| 3 | EURUSD | 0.2455 | -0.4904 | -1.9980 |
| 4 | EURUSD | -0.2297 | 0.4564 | -1.9866 |
| 5 | EURUSD | 0.4281 | -0.4494 | -1.0498 |

## PBO

- **Status:** ✅ Complete (0.0s)
- **pbo:** 0.5000
- **n_configs:** 1
- **passes_threshold:** False

## DSR

- **Status:** ✅ Complete (0.3s)
- **observed_sharpe:** 0.2961
- **deflated_sharpe:** -2.1933
- **n_trials:** 50
- **n_bars:** 9998
- **check_passed:** False
- **check_details:** DSR_NOT_SIGNIFICANT:sharpe=0.2961,expected_max=2.5908

## BOOTSTRAP

- **Status:** ✅ Complete (12.5s)
- **sharpe_ci_lower:** 0.0002
- **sharpe_ci_upper:** 0.0368
- **sharpe_point_estimate:** 0.0187
- **confidence_level:** 0.9500
- **n_resamples:** 5000

## SYNTHETIC

- **Status:** ✅ Complete (16.5s)
- **positive_rate:** 0.9850
- **n_paths:** 3000
- **mean_sharpe:** 0.3010
- **ci_lower:** 0.0356
- **ci_upper:** 0.5883
- **method:** block_bootstrap

## MONTE CARLO

- **Status:** ✅ Complete (17.5s)
- **prob_ruin:** 0.3440
- **median_ending_balance:** 5323.6033
- **p5_ending_balance:** 4062.4859
- **p95_ending_balance:** 6580.1033
- **median_max_dd_pct:** 0.1285
- **p95_max_dd_pct:** 0.2764
- **n_sims:** 5000

## STRESS

- **Status:** ✅ Complete (19.6s)
- **positive_rate:** 0.9722
- **n_paths:** 5000
- **avg_return:** 1.2337
- **avg_max_dd:** 0.4848

## Recommendation

❌ **One or more gates failed.** Strategy shows signs of:
- wfa_oos_positive: 66.7% OOS windows positive
- wfa_wfe: WFE=-0.7307
- mc_ruin_prob: P(Ruin)=34.40%
- deflated_sharpe: DSR=-2.1933
- pbo_overfitting: PBO=0.5000

**Next step:** Review failed gates. Strategy needs improvement before live deployment.
