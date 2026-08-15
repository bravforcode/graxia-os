---
title: "MRM-REGIME-CONDITIONAL — Macro Regime Mean-Reversion"
type: hypothesis
status: rejected
category: macro-regime
instrument: [xauusd]
trial_id: "1005"
registry_ref: "research/hypothesis_registry.json"
pre_reg_doc: "research/pre_registration/trial_1005_macro_regime_mr.md"
mechanism: "Real-yield CV classifies STABLE vs TRENDING regime; mean-reversion in STABLE, momentum in TRENDING."
prior_probability: low
dsr_cumulative_at_test: 2001
validation_result: REJECTED
verdict_date: "2026-07-13"
gates: {p_value: 0.2441, deflated_sharpe_pct: 0.0, wfe: 0.0, min_trades: 65}
root_cause_if_rejected: "regime-mismatch"
linked_papers: ["[[Paper_Baur_Lucey_2010_SafeHaven]]"]
linked_experiments: ["[[EXP-1005-MRM]]"]
linked_reports: ["../research/hypothesis_registry.json"]
tags: [type/hypothesis, domain/macro-regime, edge/rejected, status/rejected]
---

# MRM-REGIME-CONDITIONAL — Macro Regime Mean-Reversion

## 1. Economic Rationale
Regime-switching models outperform single-regime (academic review finding #2). MRM used *real-yield CV* to pick regime, then MR vs momentum. Per [[Paper_Baur_Lucey_2010_SafeHaven]], the *correct* safe-haven/regime trigger may be *equity-tail*, not *real-yield-CV* — which is likely why this died.

## 2. Arm Selection
| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Regime-MR** | MR in STABLE, mom in TRENDING | Regime-gated |
| B — Always-MR | Pure MR | No gate |

**Registered choice: Arm A.**

## 3. Validation Gates
| Gate | Value | Threshold | Status |
|---|---|---|---|
| p-value | 0.2441 | < 0.05 | ❌ |
| WFA OOS+ | 0.4 | ≥ 0.70 | ❌ |
| WFE | 0.0 | ≥ 0.5 | ❌ |
| Deflated Sharpe % | 0.0 | > 0.95 | ❌ |
| Min trades | 65 | ≥ 100 | ❌ |

Sharpe -1.157 = losing money.

## 4. Root Cause
**`regime-mismatch`** — the *real-yield-CV* classifier mislabeled regimes (OOS accuracy drops when classifier is fitted). Per Baur & Lucey, an *equity-tail* trigger might work where real-yield-CV did not. → **candidate for re-test with different regime definition** (requires NEW pre-registration; do not peek at holdout).

## 5. Links
- **Paper behind this:** [[Paper_Baur_Lucey_2010_SafeHaven]]
- **Experiment:** [[EXP-1005-MRM]]
- **Registry:** [hypothesis_registry.json](../research/hypothesis_registry.json)
