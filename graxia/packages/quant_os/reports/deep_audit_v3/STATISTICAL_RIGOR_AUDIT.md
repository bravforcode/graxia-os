# PHASE 6 — STATISTICAL RIGOR AUDIT
*Per R1–R18, R10. Tier 2.*

---

## 6.1 — Sample Size Assessment
- Costed run: **67 trades** (`SUMMARY.md:12`). Protocol minimum: **200 OOS trades**. **FAIL by ~3×.**
- 1-min autocorrelation: `[not accounted for]` → effective N even smaller.

## 6.2 — P-Value Distribution
- `[NO p-value reported in any artifact]`. One-tailed/two-tailed, normality assumption — all moot.

## 6.3 — Bootstrap / Monte Carlo
- `core/monte_carlo.py`, `backtest/risk_of_ruin.py`, `validation/bootstrap_sensitivity.py` exist → capability present. **Bootstrap result reported `[no]`.** Monte Carlo permutation test = Phase 13.1 label-shuffle (built, not run).

## 6.4 — Out-of-Sample Evidence
- Held-out test set touched exactly once: `[UNVERIFIABLE without hypothesis log]`. The 7-day window is too short for a meaningful IS/OOS split that isn't dominated by single-day variance.

## 6.5 — Walk-Forward Methodology Validity
- `walk_forward.py:85` default `mode="rolling"`, `is_ratio=0.7`. Structurally OK.
- Per-fold independent tuning: `optimize_func` runs on IS only (`walk_forward.py:170`). ✓
- **No gap between IS and OOS** (`walk_forward.py:138-139`) → autocorrelation bleed. → P2.
- Parameter stability fold-to-fold: `[not reported]`.

## 6.6 — Known Biases
| Bias | Present? | Evidence |
|---|---|---|
| Lookahead | PARTIAL (paths clean, gaps unverified) | Phase 1 |
| Survivorship | N/A (single instrument) | — |
| Overfitting | **LIKELY** | 67 trades, no correction, uncosted suite |
| Selection bias | **LIKELY** | no hypothesis log, only best reported |
| Cost underestimation | **YES** | slippage≡spread bug (Phase 3.2) |
| Slippage underestimation | **YES** | same |
| Data snooping | **LIKELY** | many features, no correction |
| Regime selection | **YES** | 7-day calm window (R18) |
| Fill assumption | PARTIAL | gap-through unhandled (Phase 4.4) |

## 6.7 — PBO via CSCV
`validation/probability_overfitting.py` exists → module present. **Result reported `[no]`.** → true overfitting probability unknown.

## 6.8 — Reality Check / SPA
`[NOT FOUND]`. → P3.

## 6.9 — Confidence Intervals
- `[NO CI reported alongside any Sharpe/win-rate/return]`. Every headline number is a bare point estimate → per protocol must be flagged `[POINT ESTIMATE WITHOUT CI]`.

---

## Phase 6 — Verdict

**STATUS: FAIL.** Sample size below threshold (67 < 200), no p-values, no CIs, no bootstrap, no PBO, no multiple-testing correction. The statistical machinery *exists as code* but has **not been run to produce a defensible conclusion.** "58.2% accuracy on 67 trades" is not a statistical claim; it is an observation.
