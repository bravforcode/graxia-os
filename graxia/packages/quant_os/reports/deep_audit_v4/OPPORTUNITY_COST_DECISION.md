# PHASE 24 — OPPORTUNITY COST & GO/NO-GO DECISION
**Date:** 2026-07-06 | **Auditor:** Final Synthesis Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md
**Classification:** **PIVOT-FEATURE-SPACE**

---

## 24.1 Cumulative Multiple-Testing Tally

The MetaTrader/R research ecosystem notoriously confounds discovered strategies with genuine edges. Every decision point adds a hypothesis test:

| Category | Hypotheses Tested | Bonferroni α (0.05 / count) |
|----------|-------------------|------------------------------|
| Strategy type selection (MTM, MRM, MLB chosen from N considered) | ~5-10 | — |
| Feature selection (36+ features, which subset to use?) | ~30-100 | — |
| Model hyperparameters (XGBoost params via Optuna — ~100 trials) | ~100 | — |
| Ensemble weights (MTM 0.40, MRB 0.25, MLB 0.35 — how many tried?) | ~10-50 | — |
| Ensemble thresholds (0.60, 0.40 — how many tested?) | ~5-20 | — |
| Walk-forward parameters (window size, retrain frequency) | ~5-10 | — |
| Cost model parameters (spread, slippage assumptions) | ~3-5 | — |
| Strategy variants (ADX filters, regime detection thresholds) | ~5-10 | — |
| **Conservative estimate** | **~160–300 hypotheses** | **α_corrected ≈ 0.0003** |

**Not a single multiple-testing correction has been applied** (`STATISTICAL_RIGOR_AUDIT.md:12`). At 300 hypotheses with α=0.05, the expected number of false positives is 15. A strategy with p=0.01 "significance" (Sharpe ~1.0) should be corrected to p≈0.99 after Benjamini-Hochberg.

**The probability that any single strategy's reported performance is a Type I error approaches 1.0.**

---

## 24.2 Sunk Cost Assessment

### Code Investment
| Asset | Magnitude | Assessment |
|-------|-----------|------------|
| Python source files | ~300+ .py files across ~25 packages | Massive codebase for a single-developer project |
| Backtest engine | ~1200+ line BacktestEngine | Sophisticated but P&L was 100× off for XAUUSD |
| ML pipeline | ~3 training scripts with 500-800 lines each | Extensive but heavy overlap, non-deterministic until fix |
| Strategy code | 3 strategies + ensemble | Moderate complexity |
| Audit reports | 100+ reports across v3/v4 | Extensive third-party analysis applied |

### Evidence Accumulated
| Evidence | Strength | Notes |
|----------|----------|-------|
| RESEARCH_LOG.md | **1 completed experiment** | EXP-001: "Net -$1,225 vs BH +$2,888. Sharpe 0.3" — the ONLY experiment recorded |
| Walk-forward validation | 2 instruments (XAUUSD, EURUSD) out of 15 | Cost model now correct (post-fix), but OOS edge still unverified |
| Label shuffling | **Never run on actual strategy data** | Test exists but uses synthetic data only |
| Adversarial stress testing | **Not performed** | No full-pipeline null distribution |
| Deflated Sharpe Ratio | **Not computed** | Cannot compare to "best of N trials" null |
| DSR/PBO | **Not computed** | Probability of backtest overfitting unknown |

---

## 24.3 Forward-Looking Classification

### Classification: **PIVOT-FEATURE-SPACE**

Based on 24 audit phases of evidence, the honest classification is:

**The system has NO VERIFIED EDGE.** Seven critical findings independently invalidate any confidence in backtest performance:

| # | Finding | Impact on Edge Claim |
|---|---------|---------------------|
| 1 | P&L calculation was 100× wrong for XAUUSD (`backtest/engine.py:1099`) | Any reported Sharpe from historical runs is wrong |
| 2 | Ensemble had no stop-loss — (None, None) for every signal | Adversarial selection of bad exits inflates returns |
| 3 | Walk-forward cost was hardcoded at 2350.0 | All costs wrong for non-XAUUSD instruments |
| 4 | Auto-retrain had dummy evaluation (hardcoded 1.0) | Models preserved even when degraded |
| 5 | All ML training was non-deterministic (n_jobs=-1) | Reproduction impossible |
| 6 | RESEARCH_LOG.md has exactly 1 experiment — a failed baseline | No iterative scientific validation |
| 7 | Never survived full-pipeline label shuffling | Cannot rule out "all signal is noise" |

**Even after fixing all 13 P0 bugs**, the system returns to a state where it **could discover an edge** — not one where an edge is verified. The fixes correct measurement and safety, not strategy alpha. You cannot build a house on a broken measuring tape and then claim the foundation is solid even after fixing the tape.

### Why "PIVOT-FEATURE-SPACE" not "STOP"

A full STOP would be appropriate if:
- The underlying market hypothesis was falsified (it wasn't — it was never properly tested)
- The technology stack was fundamentally flawed (it isn't — MT5/Pepperstone integration works)
- The developer lacked capacity to continue (unknown)

"PIVOT-FEATURE-SPACE" means:
1. **Reset the hypothesis log**: Start from EXP-002 with a clean slate
2. **One strategy, one instrument, one hypothesis**: Don't run 3 strategies × 15 instruments × N feature sets
3. **Measure FIRST, then optimize**: Compute DSR on a single clean walk-forward before tuning ANY hyperparameters
4. **Pre-commit to kill criteria**: "If OOS Sharpe < 0 after 6 months paper trading, archive the strategy and start fresh"
5. **Fix measurement BEFORE searching**: With corrected P&L, cost model, and SL/TP logic, the backtest engine is now capable of honest measurement — use it

---

## 24.4 Expected Value vs. Passive Benchmark

### If you deploy $10,000 real capital TODAY:

| Scenario | Probability | Expected Annual Return |
|----------|-------------|------------------------|
| Strategy has zero edge after costs (most likely) | ~90% | -5% to -15% (spread bleed + occasional SL hits) |
| Strategy has marginal edge (Sharpe 0.3 gross, ~0 net) | ~9% | -2% to +2% |
| Strategy has genuine edge (Sharpe > 1.0 net) | ~1% | +15% to +25% |
| **Expected value** | | **~ -4% to -10%** |

**Compare to:**
- S&P 500 passive: ~+10% historical annualized (no effort)
- MSCI World: ~+8% historical
- Cash in savings: ~4-5% currently

**The passive benchmark has a higher expected return than deploying real capital today, with zero operational risk.**

---

## 24.5 Kill Criteria (Must Be Established Before Real Capital)

The CONSTITUTION.md should require a pre-committed set of kill criteria. None exist:

| Criterion | Currently Defined? | Proposal |
|-----------|-------------------|----------|
| "Stop if live Sharpe < 0 after 500 trades" | ❌ NO | Adopt SPRT with H0: Sharpe ≤ 0, α=0.05, β=0.20 |
| "Stop if max drawdown exceeds 15%" | ✅ YES | Keep |
| "Stop if model drift PSI > 0.25 for 7 consecutive days" | ❌ NO | Wire DriftMonitor output to kill switch |
| "Stop if broker changes spreads/fees by >50%" | ❌ NO | Monitor `execution/cost_model.py` against live fills |
| "Stop if any P0 bug discovered post-deployment" | ❌ NO | Auto-pause on unhandled exception in trading loop |
| "Review go/continue after 6 months regardless of performance" | ❌ NO | Schedule mandatory review |

---

## 24.6 Key Phase 24 Findings

| # | Severity | Finding |
|---|----------|---------|
| 1 | **FATAL** | ~300 hypotheses tested with zero multiple-testing correction — any "edge" is a statistical artifact |
| 2 | **FATAL** | P&L was wrong (100× for XAUUSD), costs were wrong (hardcoded 2350), ensemble had no SL — ALL reported Sharpe from prior runs is invalid |
| 3 | **FATAL** | RESEARCH_LOG.md has 1 experiment — a failed baseline. Edge claim has zero scientific evidence |
| 4 | **FATAL** | Never survived a full-pipeline label shuffling test |
| 5 | **CRITICAL** | Expected value of deploying real capital today is negative vs. passive benchmark |
| 6 | **CRITICAL** | No pre-committed kill criteria for edge failure |

---

## 24.7 Decision

| Option | Recommendation |
|--------|---------------|
| Deploy real capital now | **NO** — expected negative return |
| Paper trade as-is | **NO** — paper trading without verified edge accumulates no useful signal |
| Paper trade AFTER fixing measurement + running 1 clean walk-forward | **MAYBE** — but only with pre-committed kill criteria |
| Reset: 1 strategy, 1 instrument, clean measurement, DSR-first | **YES** — this is "PIVOT-FEATURE-SPACE" |

**The 13 P0 fixes applied in this audit were necessary but not sufficient.** They fixed your measuring equipment. Now go measure something real.
