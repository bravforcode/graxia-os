# Validation Report — 20260707_212833

## Summary
- **Assets:** XAUUSD, EURUSD
- **Total Time:** 107.1s
- **Overall Verdict:** ❌ **FAIL**
- **Gates:** 4/9 PASS

## Gate Results

| Gate | Status | Metric | Threshold | Details |
|------|--------|--------|-----------|---------|
| wfa_oos_positive | ❌ FAIL | 0.6250 | 0.7000 | 62.5% OOS windows positive |
| wfa_wfe | ❌ FAIL | -0.0044 | 0.5000 | WFE=-0.0044 |
| wfa_degradation | ✅ PASS | 0.0000 | 0.3000 | Degradation=0.0% |
| mc_ruin_prob | ✅ PASS | 0.0436 | 0.0500 | P(Ruin)=4.36% |
| mc_drawdown_p95 | ✅ PASS | 0.1101 | 0.2500 | 95th percentile DD=11.0% |
| deflated_sharpe | ❌ FAIL | -2.2781 | 0.0000 | DSR=-2.2781 |
| pbo_overfitting | ❌ FAIL | 0.5000 | 0.5000 | PBO=0.5000 |
| stress_test | ✅ PASS | 0.9028 | 0.8000 | 90.3% scenarios positive |
| bootstrap_sharpe_ci | ❌ FAIL | -0.0048 | 0.0000 | Sharpe CI lower=-0.0048 |

## WFA

- **Status:** ✅ Complete (0.1s)
- **oos_consistency:** 0.6250
- **walk_forward_efficiency:** -0.0044
- **overfitting_score:** 0.0000
- **avg_is_sharpe:** 0.0673
- **avg_oos_sharpe:** 0.2057
- **n_windows:** 16

### Walk-Forward Windows

| Window | Symbol | IS Sharpe | OOS Sharpe | WFE |
|--------|--------|-----------|------------|-----|
| 0 | XAUUSD | 0.3688 | 0.0055 | 0.0150 |
| 1 | XAUUSD | 1.3852 | 0.7350 | 0.5306 |
| 2 | XAUUSD | -0.0921 | 0.2638 | -2.8651 |
| 3 | XAUUSD | -0.3546 | -0.0816 | 0.2302 |
| 4 | XAUUSD | 0.6996 | 0.6588 | 0.9417 |
| 5 | XAUUSD | 0.8288 | 0.4331 | 0.5225 |
| 6 | XAUUSD | -0.1967 | -1.4882 | 7.5648 |
| 7 | XAUUSD | -0.2258 | 1.0445 | -4.6268 |
| 0 | EURUSD | 0.9131 | -0.4560 | -0.4994 |
| 1 | EURUSD | 1.0413 | 1.0467 | 1.0051 |
| 2 | EURUSD | -0.7859 | -0.8964 | 1.1406 |
| 3 | EURUSD | -0.8529 | 1.6695 | -1.9575 |
| 4 | EURUSD | -0.1370 | 0.4044 | -2.9508 |
| 5 | EURUSD | 0.1215 | 0.0893 | 0.7348 |
| 6 | EURUSD | -0.6618 | -0.0067 | 0.0101 |
| 7 | EURUSD | -0.9747 | -0.1299 | 0.1333 |

## PBO

- **Status:** ✅ Complete (0.0s)
- **pbo:** 0.5000
- **n_configs:** 1
- **passes_threshold:** False

## DSR

- **Status:** ✅ Complete (0.4s)
- **observed_sharpe:** 0.2112
- **deflated_sharpe:** -2.2781
- **n_trials:** 50
- **n_bars:** 9958
- **check_passed:** False
- **check_details:** DSR_NOT_SIGNIFICANT:sharpe=0.2112,expected_max=2.5908

## BOOTSTRAP

- **Status:** ✅ Complete (15.6s)
- **sharpe_ci_lower:** -0.0048
- **sharpe_ci_upper:** 0.0309
- **sharpe_point_estimate:** 0.0133
- **confidence_level:** 0.9500
- **n_resamples:** 5000

## MONTE CARLO

- **Status:** ✅ Complete (43.5s)
- **prob_ruin:** 0.0436
- **median_ending_balance:** 5084.9089
- **p5_ending_balance:** 4613.8736
- **p95_ending_balance:** 5555.9251
- **median_max_dd_pct:** 0.0514
- **p95_max_dd_pct:** 0.1101
- **n_sims:** 10000

## SYNTHETIC

- **Status:** ✅ Complete (104.2s)
- **positive_rate:** 0.8977
- **n_paths:** 3000
- **mean_sharpe:** 0.2134
- **ci_lower:** -0.1186
- **ci_upper:** 0.5480
- **method:** block_bootstrap

## STRESS

- **Status:** ✅ Complete (106.6s)
- **positive_rate:** 0.9028
- **n_paths:** 5000
- **avg_return:** 0.3208
- **avg_max_dd:** 0.2079

## Recommendation

❌ **One or more gates failed.** Strategy shows signs of:
- wfa_oos_positive: 62.5% OOS windows positive
- wfa_wfe: WFE=-0.0044
- deflated_sharpe: DSR=-2.2781
- pbo_overfitting: PBO=0.5000
- bootstrap_sharpe_ci: Sharpe CI lower=-0.0048

**Next step:** Review failed gates. Strategy needs improvement before live deployment.
