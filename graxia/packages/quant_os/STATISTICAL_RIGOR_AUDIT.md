# STATISTICAL_RIGOR_AUDIT.md — Phase 6

## 6.1 — Sample Size Assessment

- **Walk-forward folds**: Default 5 folds in `scripts/run_multi_symbol_wf.py:96`, 3 windows in `ml/pipeline.py:346`
- **Minimum trades**: No systematic minimum enforced. Backtest engine generates whatever the strategy produces.
- **Autocorrelation adjustment**: NOT performed on effective sample size. **P2 FINDING**.

## 6.2 — P-Value Distribution Audit

- P-values computed in `validation/signal_validator.py:323-350` via t-test on early vs late Sharpe
- One-tailed vs two-tailed: Two-tailed t-test used (scipy default). **PASS**.
- p-hacking check: Not systematically performed. **[UNVERIFIED]**

## 6.3 — Bootstrap / Monte Carlo

- `core/risk/monte_carlo.py` — Monte Carlo simulation for ruin probability exists
- `validation/overfitting_detector.py` — bootstrap resampling for overfitting detection
- `core/monte_carlo.py` — equity path simulation
- **PASS** — Monte Carlo infrastructure exists and is wired into validation pipeline

## 6.4 — Out-of-Sample Evidence

- Walk-forward provides genuine OOS folds with embargo gaps (`core/cross_validation.py:86-108`)
- Holdout validation in `core/holdout_validation.py` — separate dev/holdout split
- **PASS** — OOS methodology is sound where applied (XAUUSD, EURUSD only)

## 6.5 — Walk-Forward Methodology Validity

- **Expanding window**: `validation/walk_forward.py:55-74` — train grows, test advances
- **Embargo**: Default 12 bars between IS and OOS — prevents autocorrelation bleed. **PASS**
- **Same preprocessing per fold**: Feature engineering is re-run per fold in `validation/walk_forward.py:331-370`. **PASS**
- **Parameter stability**: WFE (Walk-Forward Efficiency) computed in `backtest/walk_forward.py:257-260`. No systematic threshold enforced. **P2 FINDING**.

## 6.6 — Known Statistical Biases

| Bias Type | Present? | Evidence |
|-----------|----------|----------|
| Lookahead bias | **YES** (P1) | `strategies/mlb.py:328-329` center=True |
| Survivorship bias | **UNVERIFIED** | No evidence of instrument selection bias check |
| Overfitting to data sample | **UNVERIFIED** | PBO/DSR exist but not systematically applied to all strategies |
| Selection bias | **UNVERIFIED** | No hypothesis log maintained |
| Transaction cost underestimation | **YES** (P0) | Metals commission double-count |
| Slippage underestimation | **YES** (P2) | Bar-level fills, no tick-level validation |
| Data snooping | **YES** (P2) | ~41 features tested without Bonferroni correction |
| Regime selection bias | **UNVERIFIED** | Backtest period coverage not analyzed per instrument |
| Fill assumption bias | **YES** (P2) | No slippage-through-level for stops |

## 6.7 — Probability of Backtest Overfitting (PBO) via CSCV

- **Implemented**: `validation/probability_overfitting.py:59-94` — `calculate_pbo_from_matrix()` using correct CSCV algorithm
- **Wired**: Into `validation/overfitting_detector.py` and `validation/pipeline/runner.py`
- **Not systematically run** on all strategies — only when explicitly invoked. **P2 FINDING**.

## 6.8 — Reality Check / SPA Test

- **NOT IMPLEMENTED** — no White's Reality Check or Hansen's SPA test exists
- **[ABSENT]** — Bonferroni/BH-FDR correction is the only multiple-testing correction available

## 6.9 — Confidence Intervals

- No confidence intervals reported on headline Sharpe ratios anywhere in the codebase
- **[POINT ESTIMATE WITHOUT CI — strength of evidence cannot be assessed]**

---

**P0 Findings**: 1 (metals cost — from Phase 3)
**P1 Findings**: 1 (center=True lookahead — from Phase 5)
**P2 Findings**: 4 (autocorrelation adjustment, WFE threshold, data snooping, no CI on Sharpe)
**P3 Findings**: 0
