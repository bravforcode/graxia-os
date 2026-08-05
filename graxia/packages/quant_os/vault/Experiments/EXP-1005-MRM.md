---
title: "EXP-1005 MRM Regime-Conditional MR"
type: experiment
status: done
hypothesis_ref: "[[HYP-MRM-REGIME-CONDITIONAL]]"
trial_id: "1005"
registry_ref: "research/hypothesis_registry.json"
runner: "scripts/run_strategy_validation.py"
data_sources: ["data/XAUUSD_D1.csv", "data/rydc/rydc_daily.csv"]
date_run: "2026-07-13"
verdict: REJECTED
gates_passed: 0
gates_failed: 6
metrics: {p_value: 0.2441, sharpe: -1.157, wfe: 0.0, n_trades: 65, deflated_sharpe_pct: 0.0}
evidence_artifact: "research/hypothesis_registry.json"
root_cause: "regime-classifier-misfit"
cost_model: "pepperstone_razor"
tags: [type/experiment, domain/macro-regime, edge/rejected, status/done, instrument/xauusd]
---

# EXP-1005 MRM Regime-Conditional MR

## 1. Hypothesis Under Test
→ [[HYP-MRM-REGIME-CONDITIONAL]]

## 2. Setup
- **Runner:** `scripts/run_strategy_validation.py`
- **Data:** XAUUSD_D1 + rycd daily (dfii10 column for regime CV)
- **Cost model:** pepperstone_razor (XAUUSD = spread-only, not the killer)

## 3. Results (from research/hypothesis_registry.json)
| Gate | Value | Threshold | Pass? |
|---|---|---|---|
| p-value | 0.2441 | < 0.05 | ❌ |
| WFA OOS+ | 0.4 | ≥ 70% | ❌ |
| WFE | 0.0 | ≥ 0.5 | ❌ |
| Deflated Sharpe % | 0.0 | > 0.95 | ❌ |
| Min trades | 65 | ≥ 100 | ❌ |

**Verdict:** REJECTED — Sharpe -1.157 = losing money. gates passed 0 / failed 6.

## 4. Root Cause
`regime-classifier-misfit`. The *real-yield CV* regime label was wrong (OOS accuracy drops when classifier is fitted). Per [[Paper_Baur_Lucey_2010_SafeHaven]], the correct safe-haven/regime trigger may be *equity-tail*, not *real-yield-CV*. That variant is UNTESTED.

## 5. External Evidence
- [hypothesis_registry.json](../research/hypothesis_registry.json)
- [FOREX_EDGE_INVESTIGATION.md](../FOREX_EDGE_INVESTIGATION.md) (regime-filter interaction note)

## 6. Follow-up
- Candidate re-test: define regime via equity-return-5th-percentile (Baur & Lucey), NOT real-yield CV. **Requires new pre-registration** — do not relax gates or peek at holdout.
