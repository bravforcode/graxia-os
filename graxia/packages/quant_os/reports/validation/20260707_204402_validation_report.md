# Validation Report — 20260707_204402

## Summary
- **Assets:** XAUUSD, EURUSD
- **Total Time:** 19.5s
- **Overall Verdict:** ❌ **FAIL**
- **Gates:** 5/9 PASS

## Gate Results

| Gate | Status | Metric | Threshold | Details |
|------|--------|--------|-----------|---------|
| wfa_oos_positive | ❌ FAIL | 0.5833 | 0.7000 | 58.3% OOS windows positive |
| wfa_wfe | ✅ PASS | 0.9633 | 0.5000 | WFE=0.9633 |
| wfa_degradation | ✅ PASS | 0.0000 | 0.3000 | Degradation=0.0% |
| mc_ruin_prob | ✅ PASS | 0.0454 | 0.0500 | P(Ruin)=4.54% |
| mc_drawdown_p95 | ✅ PASS | 0.1103 | 0.2500 | 95th percentile DD=11.0% |
| deflated_sharpe | ❌ FAIL | -2.2781 | 0.0000 | DSR=-2.2781 |
| pbo_overfitting | ❌ FAIL | 0.5000 | 0.5000 | PBO=0.5000 |
| stress_test | ✅ PASS | 0.9090 | 0.8000 | 90.9% scenarios positive |
| bootstrap_sharpe_ci | ❌ FAIL | -0.0051 | 0.0000 | Sharpe CI lower=-0.0051 |

## WFA

- **Status:** ✅ Complete (0.1s)
- **oos_consistency:** 0.5833
- **walk_forward_efficiency:** 0.9633
- **overfitting_score:** 0.0000
- **avg_is_sharpe:** 0.0238
- **avg_oos_sharpe:** 0.2469
- **n_windows:** 12

### Walk-Forward Windows

| Window | Symbol | IS Sharpe | OOS Sharpe | WFE |
|--------|--------|-----------|------------|-----|
| 0 | XAUUSD | 0.1571 | 1.2324 | 7.8430 |
| 1 | XAUUSD | 0.6763 | 0.4253 | 0.6289 |
| 2 | XAUUSD | -0.0943 | -0.7627 | 8.0879 |
| 3 | XAUUSD | 0.7172 | 0.5816 | 0.8110 |
| 4 | XAUUSD | 0.4772 | -0.6782 | -1.4212 |
| 5 | XAUUSD | -0.8077 | 1.1436 | -1.4159 |
| 0 | EURUSD | 0.6679 | 0.6761 | 1.0122 |
| 1 | EURUSD | 0.5213 | -1.0193 | -1.9555 |
| 2 | EURUSD | -0.7131 | 1.0134 | -1.4210 |
| 3 | EURUSD | -0.4771 | 0.8557 | -1.7933 |
| 4 | EURUSD | -0.2588 | -0.1467 | 0.5666 |
| 5 | EURUSD | -0.5803 | -0.3578 | 0.6166 |

## PBO

- **Status:** ✅ Complete (0.1s)
- **pbo:** 0.5000
- **n_configs:** 1
- **passes_threshold:** False

## DSR

- **Status:** ✅ Complete (0.5s)
- **observed_sharpe:** 0.2112
- **deflated_sharpe:** -2.2781
- **n_trials:** 50
- **n_bars:** 9958
- **check_passed:** False
- **check_details:** DSR_NOT_SIGNIFICANT:sharpe=0.2112,expected_max=2.5908

## BOOTSTRAP

- **Status:** ✅ Complete (12.3s)
- **sharpe_ci_lower:** -0.0051
- **sharpe_ci_upper:** 0.0314
- **sharpe_point_estimate:** 0.0133
- **confidence_level:** 0.9500
- **n_resamples:** 5000

## SYNTHETIC

- **Status:** ✅ Complete (15.9s)
- **positive_rate:** 0.8993
- **n_paths:** 3000
- **mean_sharpe:** 0.2128
- **ci_lower:** -0.1119
- **ci_upper:** 0.5401
- **method:** block_bootstrap

## MONTE CARLO

- **Status:** ✅ Complete (17.1s)
- **prob_ruin:** 0.0454
- **median_ending_balance:** 5086.0990
- **p5_ending_balance:** 4616.6540
- **p95_ending_balance:** 5547.5859
- **median_max_dd_pct:** 0.0511
- **p95_max_dd_pct:** 0.1103
- **n_sims:** 5000

## STRESS

- **Status:** ✅ Complete (19.0s)
- **positive_rate:** 0.9090
- **n_paths:** 5000
- **avg_return:** 0.3223
- **avg_max_dd:** 0.2062

## Recommendation

❌ **One or more gates failed.** Strategy shows signs of:
- wfa_oos_positive: 58.3% OOS windows positive
- deflated_sharpe: DSR=-2.2781
- pbo_overfitting: PBO=0.5000
- bootstrap_sharpe_ci: Sharpe CI lower=-0.0051

**Next step:** Review failed gates. Strategy needs improvement before live deployment.
