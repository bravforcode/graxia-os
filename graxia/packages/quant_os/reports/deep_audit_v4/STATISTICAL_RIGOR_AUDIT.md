# STATISTICAL RIGOR AUDIT — Phase 6
**Date:** 2026-07-05 | **Auditor:** Strategist Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md

---

## 6.1 — Sample Size Assessment

### Backtest Data

| Instrument | M1 Rows | H1 Rows | D1 Rows | W-F Run? |
|------------|---------|---------|---------|----------|
| EURUSD | 5,001 | ~3,500 | ~3,500 | YES (buggy) |
| XAUUSD | 5,001 | ~3,500 | ~3,500 | YES (buggy) |
| 13 others | 5,001 each | ~3,500 each | ~3,500 each | NO |

Source: `reports/deep_audit_v4/DOC_CODE_CONTRADICTION_AUDIT.md:89-101`

### Effective Sample Size
For 1-min data with autocorrelation:
- 5,001 bars ≈ 3.5 trading days of 1-min data
- At typical intraday autocorrelation (ρ ≈ 0.05-0.15), effective sample size: N_eff ≈ N × (1-ρ)/(1+ρ) ≈ **2,200-4,300**
- `scripts/walk_forward.py:333-334` defaults: `--train-window 500`, `--test-window 200`, `--step 200`
  - 5,001 rows → ~22 folds of train=500/test=200

### Trade Count Assessment

| Criterion | Threshold | Evidence | Status |
|-----------|-----------|----------|--------|
| OOS trades total | < 200 = insufficient | `scripts/walk_forward.py:260` — `total_trades = sum(f["n_trades"])` | UNVERIFIED — no saved walk-forward results with trade counts |
| Per-fold trades | Depends on confidence threshold | `walk_forward.py:81-93` — mask = `confs >= min_confidence` (default 0.85) | With default 0.85, trade density is ~5-15% of bars → ~10-30 per fold |

**Verdict**: `[INSUFFICIENT EVIDENCE]` — Trade counts depend on run-time parameters. With 5,001 bars and 0.85 confidence, typical trade count per fold is well below 30 (the HoldoutValidator minimum at `core/holdout_validation.py:108`). The walk-forward script's own minimum is `n_trades >= 3` per fold for considering a fold "positive" (`scripts/walk_forward.py:262`), which is far too low.

### Strategy-Level Trade Counts
- `reports/deep_audit_v4/AUDIT_INDEX.md:22-25`: All 4 strategies rated `INSUFFICIENT EVIDENCE` — no walk-forward OOS validation confirmed

---

## 6.2 — P-Value Distribution Audit

### Where P-Values Appear

| Location | Usage | Correct? |
|----------|-------|----------|
| `scripts/diagnose_features.py:124` | `pearsonr()` p-value per feature | YES — but Bonferroni-corrected alpha applied |
| `scripts/diagnose_features.py:126` | `spearmanr()` p-value per feature | YES — but Bonferroni-corrected alpha applied |
| `scripts/apply_dsr_pbo.py:52-57` | Label shuffling p-value | YES — permutation-based |
| `core/signal_filter.py:107-116` | Monte Carlo p-value check vs `max_p_value` | YES — but threshold unexamined |
| `core/holdout_validation.py:101` | Deflated Sharpe z-score → implicit p-value | PARTIAL — uses normal approximation |

### P-Value Quality

| Check | Status |
|-------|--------|
| One-tailed vs two-tailed | `pearsonr`/`spearmanr` return **two-tailed** by default — overconservative for directional trading signals |
| Normal assumption validated? | Deflated Sharpe (`core/holdout_validation.py:139-187`) assumes normal (z-score) — normality of trade returns **never tested** |
| P-hacking check | NOT PERFORMED — no p-value histogram or p-curve analysis to detect publication bias |
| Correction for threshold sweeps | `scripts/walk_forward.py:386` — loops over confidence thresholds but no correction for multiple thresholds |

### Deflated Sharpe Ratio — Two Competing Implementations

| File | Formula | Differences |
|------|---------|-------------|
| `core/holdout_validation.py:139-187` | `(SR_obs - E[max_SR]) / std[max_SR]` | Uses `n_trades` as proxy for `T`, `n_strategies × n_trials` as `N` |
| `validation/deflated_sharpe.py` (imported) | Different formula | `reports/Meta/research/DEEP_DIVE_SYNTHESIS.md:62` confirms: "Two duplicate DSR implementations... Formulas differ" |

**Verdict**: `[FAIL]` — Two different DSR formulas exist. Which one is "correct" depends on usage context. Neither is validated against the original Bailey & López de Prado (2014) derivation. The `holdout_validation.py` version uses `n_trades` as a proxy for `T` (number of observations), which is questionable — the paper uses `T` as the number of return periods, not trades.

---

## 6.3 — Bootstrap / Monte Carlo

### What Exists

| Technique | Implementation | Status |
|-----------|---------------|--------|
| Bootstrap equity paths | `core/risk/monte_carlo.py:bootstrap_equity_paths()` | ✅ EXISTS |
| Monte Carlo trade permutation | `core/monte_carlo.py:124` — `shuffle` mode "random permutation of trades" | ✅ EXISTS (deprecated module) |
| Label shuffling | `tests/test_label_shuffling.py:20-67`, `scripts/apply_dsr_pbo.py:97-175` (10,000 permutations) | ✅ EXISTS |
| Monte Carlo in signal filter | `core/signal_filter.py:107-116` — `mc.p_value < self.max_p_value` | ✅ EXISTS, wired |
| Bootstrap backtest results | NOT FOUND — no block-bootstrap of returns series | ❌ MISSING |
| Monte Carlo confidence intervals on Sharpe | NOT FOUND — no CI on any performance metric | ❌ MISSING |

### Label Shuffling Gap
- `reports/deep_audit_v4/AUDIT_INDEX.md:147-150`: "Current test uses synthetic data only"
- `tests/test_label_shuffling.py:43` — uses `np.random.permutation(labels)` on synthetic features/labels
- **Not run against actual strategy features and live targets**

**Verdict**: `[PARTIAL]` — Bootstrap and Monte Carlo infrastructure exists but:
1. Label shuffling never validated against real data
2. No bootstrap confidence intervals on any headline metric
3. No block-bootstrap to account for autocorrelation
4. Monte Carlo module is deprecated (`core/monte_carlo.py:1`)

---

## 6.4 — Out-of-Sample Evidence

### Test Set Discipline

| Check | Status | Source |
|-------|--------|--------|
| Held-out test set defined | YES | `validation/dataset_protocol.py:63-69` — `default_xauusd()` defines train/val/holdout splits |
| Test set touched exactly once? | ENFORCED BY CONVENTION | `validation/dataset_protocol.py:47-51` — `mark_holdout_used()` sets flag; `is_holdout_used()` checks it |
| How many times evaluated? | Unknown — convention, not automated gate | `validation/test_dataset_protocol.py:35` tests the protocol but no enforcement in backtest pipeline |
| Train/val/holdout dates | Hardcoded placeholders: `2020-01-01` to `2026-06-30` | `dataset_protocol.py:66-68` — comment says "User must fill actual dates" |

### Walk-Forward OOS
- `scripts/walk_forward.py:150-298` — uses rolling folds within a single dataset
- **The "test" in walk-forward is a sequential OOS fold, not an independent holdout**
- No evidence of a final, post-all-development, held-out test set evaluation with locked test set

**Verdict**: `[INSUFFICIENT EVIDENCE]` — The holdout protocol infrastructure exists but:
1. Dates are placeholders
2. Test set access tracking is convention-based, not enforced in backtest pipeline
3. No evidence of a final locked-holdout evaluation having been performed

---

## 6.5 — Walk-Forward Methodology Validity

### Implementations

| File | Type | Window Type | Purge/Embargo | Hyperparameter Tuning |
|------|------|-------------|---------------|----------------------|
| `scripts/walk_forward.py` | XGBoost WF | Rolling row-count | ❌ NO GAP (`train_end → test_end` at `:174`) | Fixed params per run |
| `backtest/walk_forward.py` | Strategy WF | Rolling/Anchored | ✅ YES (`purge_bars`, `embargo_bars` at `:109-110`) | `optimize_func` arg |
| `strategies/walk_forward.py` | Strategy WF | Rolling with embargo | ✅ YES (`embargo_bars` at `:111`) | Manual via `optimize_func` |
| `validation/walk_forward.py` | Strategy WF | Time-split | ✅ YES (`:25` — embargo parameter) | Unknown |

### Critical Issue: No Purge Gap in Primary Walk-Forward Script
`scripts/walk_forward.py:172-175`:
```python
train_end = train_start + train_window
test_end = train_end + test_window
```
- **Train ends at bar N, test starts at bar N** — zero gap
- This creates direct autocorrelation bleed: bar N's features include bar N's own close, and bar N's target is computed from `close.shift(-forward_bars)` — but XGBoost prediction at bar N uses all those features
- `backtest/walk_forward.py` has `purge_bars` parameter (`:109`) but defaults to `purge_bars=0` (`:109`)

### Parameter Stability
- `backtest/walk_forward.py:325-352` — `_compute_parameter_stability()` computes CV across folds
  - CV < 15% = high stability, > 30% = fragile
- **Actual stability scores: UNVERIFIED** — no walk-forward result file shows per-parameter CV

### Feature Selection / Normalization Within Each Fold
- `scripts/walk_forward.py:162` — `data = df[feature_cols].fillna(0).values` — features selected once, BEFORE folds
- `core/ml_pipeline.py:147-155` — `fit_scaler` docs say "CRITICAL: Call ONLY on training data"
- **Unknown** whether scaler is re-fit per fold or globally — `scripts/walk_forward.py` does NOT use scaler

**Verdict**: `[FAIL]` — The primary walk-forward script (`scripts/walk_forward.py`) has no purge gap, no independent hyperparameter optimization within folds, no feature normalization, and no parameter stability tracking. The more rigorous `backtest/walk_forward.py` exists but its actual execution output is not preserved.

---

## 6.6 — Known Statistical Biases

| Bias | Description | Status in quant_os | Severity |
|------|-------------|-------------------|----------|
| **Survivorship** | Only instruments that still exist are backtested | EURUSD+BTCUSD — no delisted pair issue, but single-instrument focus | LOW |
| **Lookahead** | Using future information | Purge gap absent in `scripts/walk_forward.py`; FVG 1-bar lookahead in detection | **MEDIUM** |
| **Selection bias (p-hacking)** | Testing many configs, reporting best | `ParamSweep` tests all combos, picks best — no multiple-testing correction | **HIGH** |
| **Overfitting (IS→OOS)** | Strategy fitted to noise | IS→OOS degradation not consistently measured; WFE tracked in `backtest/walk_forward.py` only | **HIGH** |
| **Sample size** | Too few trades for inference | 5,001 bars M1 → ~22 folds × 500 train bars → 10-30 trades/fold at 0.85 conf | **HIGH** |
| **Data snooping** | Entire dataset used for feature engineering | Features hardcoded in scripts — no evidence of iterative dataset reuse | MEDIUM |
| **Transaction cost** | Costs underestimated or misapplied | `scripts/walk_forward.py:111` — cost uses `price_mult` derived from mean price, not per-bar | **HIGH** |
| **Autocorrelation** | Return autocorrelation inflates Sharpe | Annualization uses √(252×1440) — assumes i.i.d. 1-min returns | **HIGH** |
| **Non-normality** | Sharpe assumes normal returns | Never tested; Deflated Sharpe uses z-score (normal assumption) | MEDIUM |
| **Benchmark cherry-picking** | Comparing against weak benchmark | No benchmark comparison in strategy evaluation | MEDIUM |
| **Publication bias** | Only successful experiments documented | RESEARCH_LOG.md has 3 entries, 2 "NOT STARTED" | LOW |

---

## 6.7 — PBO via CSCV

### Implementation Status

| File | Method | Quality |
|------|--------|---------|
| `validation/probability_overfitting.py:59-170` | CORRECT CSCV — strategy matrix: N configs × S periods | ✅ PROPER implementation |
| `scripts/tsm_validate.py:245-360` | CSCV — S=10 subsets, C(10,5)=252 combos | ✅ PROPER implementation |
| `scripts/tsm_ensemble_backtest.py:421-460` | CSCV on ensemble portfolio returns | ✅ PROPER implementation |
| `scripts/tsm_ensemble_backtest_4asset.py:404-460` | CSCV on 4-asset ensemble | ✅ PROPER implementation |

### Actual PBO Values
- **No PBO values preserved in repo** — the scripts exist but output files under `artifacts/walk_forward/` and similar directories are not version-controlled
- `validation/overfitting_detector.py:139-200` — `check_pbo()` exists but requires `strategy_matrix` which is not populated by the primary `scripts/walk_forward.py`

**Verdict**: `[IMPLEMENTED BUT UNVERIFIED]` — PBO via CSCV is correctly implemented in `validation/probability_overfitting.py`. The `scripts/tsm_*.py` family computes it for ensemble strategies. **But**: (1) no PBO value is preserved in the repo, (2) `scripts/walk_forward.py` (the primary ML walk-forward) does NOT call CSCV, and (3) `backtest/walk_forward.py:79` stores oos_returns for CSCV but the actual PBO calculation is never triggered within the `WalkForwardAnalyzer.analyze()` method (`backtest/walk_forward.py:127-265`).

---

## 6.8 — Reality Check / SPA Test

- **Superior Predictive Ability (SPA) test by Hansen (2005)**: NOT FOUND
- **Reality Check by White (2000)**: NOT FOUND
- Both are referenced in `reports/edge_detection_research.md` (academic review section) but not implemented

**Verdict**: `[NOT IMPLEMENTED]` — Neither White's Reality Check nor Hansen's SPA test exist. CSCV-based PBO is the only formal overfitting correction.

---

## 6.9 — Confidence Intervals

| Metric | Has CI? | Source |
|--------|---------|--------|
| Sharpe ratio | NO — point estimate only | All walk-forward and backtest output |
| Win rate | NO — raw arithmetic mean | `scripts/walk_forward.py:286-293` |
| Total PnL | NO — point estimate | `scripts/walk_forward.py:290-292` |
| Max drawdown | NO — raw maximum | `scripts/walk_forward.py:291` |
| Accuracy | NO — raw proportion | `scripts/walk_forward.py:291` |
| Deflated Sharpe threshold | Partial — uses 1.96 threshold (95% CI) | `core/holdout_validation.py:185` |

**Verdict**: `[FAIL]` — Every headline metric is reported as a bare point estimate. Zero confidence intervals. The only threshold-based confidence is the 1.96 z-cutoff in Deflated Sharpe, which presumes normality (never tested).

---

## 6. — FINAL VERDICT (Phase 6)

| Criterion | Status |
|-----------|--------|
| Sample size | INSUFFICIENT — 5,001-bar M1, <30 trades/fold at 0.85 conf |
| P-value quality | FAIL — two-tailed by default, no normality test, no p-curve, two competing DSR formulas |
| Bootstrap/Monte Carlo | PARTIAL — exists but unused on actual data, deprecated module |
| OOS evidence | INSUFFICIENT — holdout infrastructure unused, walk-forward has no purge gap |
| Walk-forward methodology | FAIL — no purge gap in primary script, hyper params not tuned per fold |
| Statistical biases | 7 of 11 biases rated MEDIUM or HIGH severity |
| PBO/CSCV | IMPLEMENTED BUT UNVERIFIED — no preserved output |
| SPA test | NOT IMPLEMENTED |
| Confidence intervals | FAIL — zero CIs on any headline metric |

**Overall**: `[FAIL]` — The statistical rigor infrastructure is partially built (DSR, CSCV, bootstrap, Monte Carlo all exist) but almost none of it is actually used to validate the primary ML walk-forward pipeline. Results are reported as bare point estimates without CIs, p-values, or multiple-testing corrections.
