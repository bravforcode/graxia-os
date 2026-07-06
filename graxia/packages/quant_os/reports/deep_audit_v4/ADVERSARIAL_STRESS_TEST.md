# PHASE 13 — ADVERSARIAL / RED-TEAM STRESS TESTING
**Quant OS Deep Audit v4.0 | Date: 2026-07-05 | Auditor: auditor agent**

---

## 13.1 Label/Target Shuffling

### Test Files Exist — But Not Full Pipeline
- **`tests/test_label_shuffling.py`**: Exists (188 lines). Uses simplified proxy: `labels × random_normal(0.001, 0.01)` for returns computation (line 79). This is NOT a full backtest replay — it's a synthetic proxy that has weak signal-to-noise.
- **`tests/test_label_shuffling_actual_data.py`**: Exists (205 lines). Loads actual features from `artifacts/features_v2/features_XAUUSD_1min.parquet`. Builds labels from target column. But still uses the same proxy `_compute_sharpe()` function — NOT a full pipeline-level backtest.

### Critical Gap
Neither test runs the FULL pipeline:
1. Generate features → 2. Train model → 3. Generate signals → 4. Execute backtest with fill/cost model → 5. Compute Sharpe

Both tests shortcut steps 2-4 with a `_compute_sharpe()` proxy that simulates returns as `labels × noise`. This:
- Ignores strategy logic (indicator calculations, entry/exit rules)
- Ignores fill model (slippage, spread, commission)
- Ignores position sizing
- Ignores walk-forward split

### Has Label Shuffling Been Run?
- **No evidence** of ≥100 permutation label-shuffle test being executed and results saved.
- The tests exist as pytest fixtures but execution results not found in artifacts.
- **P0 Finding**: Full pipeline label shuffling never executed. Cannot distinguish signal from noise at pipeline level.

---

## 13.2 Synthetic/Surrogate Data Injection

### Status: ❌ NOT IMPLEMENTED
- No `test_synthetic_data_injection.py` or equivalent found.
- No surrogate data generator with matching volatility/autocorrelation.
- **False positive risk**: Pipeline may find "signal" in pure noise due to overfitting, lookahead leakage, or multiple testing. Untested.

---

## 13.3 Cost & Friction Perturbation

### Status: ⚠️ PARTIAL
- `execution/cost_model.py:15-18`: Has 4 stress scenarios (1×, 1.5×, 2×, 3× multipliers) but these are spread+slippage scenarios for individual trades, not systematic backtest perturbation.
- No evidence of a script that reruns full backtest at 0.5×, 1×, 2×, 5× assumed costs and reports the Sharpe degradation curve.
- **R23 critical**: If strategy crosses zero net Sharpe at 2× cost, the margin of safety is thin.

---

## 13.4 Outlier/Single-Trade Sensitivity

### Status: ❌ NOT IMPLEMENTED
- No code found that systematically:
  - Removes the best trade and recomputes Sharpe
  - Removes best 1%, 5%, 10% of trades
  - Removes best week/month
  - Plots degradation curve
- Without this test, a strategy dependent on 1-2 outlier trades would appear statistically significant when it is not.

---

## 13.5 Time-Period Sensitivity

### Status: ❌ NOT IMPLEMENTED
- No leave-one-month-out cross-validation script found for full pipeline.
- No rolling-window robustness check that tests if performance is driven by a few anomalous periods (e.g., March 2020 alone accounting for 60% of returns).
- `backtest/engine.py` has walk-forward support (line 9) but no systematic sensitivity analysis script.

---

## 13.6 Parameter Perturbation Stability

### Status: ❌ NOT IMPLEMENTED
- No script found that perturbs:
  - Window sizes: ±10%, ±20%
  - Signal thresholds: ±10%, ±20%
  - SL/TP levels: ±10%, ±20%
- No Sharpe surface plotted to determine if optimum is a smooth plateau (robust) or sharp peak (fragile).
- `run_backtest_real.py` exists but appears to be a single-run script, not a perturbation harness.

---

## 13.7 Adversarial Summary Table

| Test | Status | Detail |
|---|---|---|
| Label shuffling (≥100 perms) | ❌ NOT RUN | Test files exist but use proxy, not full pipeline |
| Synthetic data injection | ❌ NOT IMPLEMENTED | No surrogate data test |
| Cost perturbation (0.5×–5×) | ❌ NOT RUN | Scenarios exist for trades, not backtest rerun |
| Outlier/single-trade sensitivity | ❌ NOT IMPLEMENTED | No leave-best-trade-out |
| Time-period sensitivity (LOMO) | ❌ NOT IMPLEMENTED | No leave-one-month-out |
| Parameter perturbation (±10–20%) | ❌ NOT IMPLEMENTED | No Sharpe surface analysis |
| Real Sharpe vs null distribution | ❌ NOT COMPUTED | p-value unknown |

**Overall Adversarial Score: 0/7 tests completed at pipeline level. ALL are P0 or HIGH severity findings.**

---

## 13.8 Per-Strategy and Ensemble-Level Testing

### Required Setup
Every adversarial test must be run 4 times:
1. MTM (Momentum/Trend) standalone
2. MRB (Mean Reversion/Breakout) standalone
3. MLB (Machine Learning Based) standalone
4. Ensemble (combined)

### MLB-Specific Concern
- `strategies/ensemble.py:472`: MLB gets 35% weight (highest after MTM's 40%).
- MLB is ML-based. ML strategies are most susceptible to:
  - Lookahead leakage (training on future data)
  - Overfitting (high feature count relative to sample size)
  - Label noise (binary classification on noisy financial returns)
- If MLB passes label shuffling when MTM/MRB fail, that's a RED FLAG for leakage, not a sign of "genuine signal."

### Status: ❌ None of these 4-strategy tests have been run.

---

## TOP FINDINGS — Phase 13

| # | Severity | Finding |
|---|---|---|
| 1 | P0 | **Label shuffling never run at full pipeline level**: Test files exist but use simplified proxy returns with random noise injection — meaningless for signal detection. |
| 2 | P0 | **Synthetic data injection never implemented**: No test verifies pipeline doesn't find fake "signal" in pure noise. |
| 3 | P0 | **Cost perturbation never run as full backtest**: No Sharpe-vs-cost degradation curve exists. |
| 4 | P0 | **Outlier sensitivity never tested**: One great trade could account for entire Sharpe. |
| 5 | P0 | **Time-period sensitivity never tested**: Performance could be driven by 1-2 anomalous periods. |
| 6 | P0 | **Parameter perturbation never tested**: No evidence the strategy is stable under parameter variation. |
| 7 | P0 | **Zero of seven adversarial tests completed**: All reported strategies lack basic robustness evidence. Any live capital deployment is premature. |
