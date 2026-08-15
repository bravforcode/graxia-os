---
title: "EXP-1001 RYDC Real-Yield Divergence"
type: experiment
status: done
hypothesis_ref: "[[HYP-RYDC-ARM-A]]"
trial_id: "1001"
registry_ref: "research/hypothesis_registry.json"
runner: "scripts/run_rydc_validation.py"
data_sources: ["data/XAUUSD_D1.csv", "data/DXY_D1.csv"]
date_run: "2026-07-12"
verdict: REJECTED
gates_passed: 0
gates_failed: 7
metrics: {p_value: 0.968, sharpe: 0.044, wfe: null, n_trades: 52, deflated_sharpe_pct: 0.16}
evidence_artifact: "research/hypothesis_registry.json"
root_cause: "contemporaneous-response-no-lag"
cost_model: "pepperstone_razor"
tags: [type/experiment, domain/macro, edge/rejected, status/done, instrument/xauusd]
---

# EXP-1001 RYDC Real-Yield Divergence

## 1. Hypothesis Under Test
→ [[HYP-RYDC-ARM-A]]

## 2. Setup
- **Runner:** `scripts/run_rydc_validation.py`
- **Data:** XAUUSD_D1, DXY_D1
- **Cost model:** pepperstone_razor — N/A for XAUUSD (spread-only, $0 commission). Cost was NOT the killer here.

## 3. Results (from research/hypothesis_registry.json)
| Gate | Value | Threshold | Pass? |
|---|---|---|---|
| p-value | 0.968 | < 0.05 | ❌ |
| WFA OOS+ | — | ≥ 70% | ❌ |
| Deflated Sharpe % | 0.16 | > 0.95 | ❌ |
| Min trades | 52 | ≥ 100 | ❌ |

**Verdict:** REJECTED — p=0.9680 = strong null. gates passed 0 / failed 7.

## 4. Root Cause
`contemporaneous-response-no-lag`. Gold's response to DXY/real-yield is *same-bar*, not lagged. The diffusion-lag tradeable mechanism does not exist. Distinct from FX cost-dominance and crypto sample-size deaths.

## 5. External Evidence
- [hypothesis_registry.json](../research/hypothesis_registry.json)
- [generation_framework.md](../research/generation_framework.md) (prior-prob reminder: RYDC p=0.9680)

## 6. Follow-up
- The *predictor* (real rates) is real per [[Paper_Pierdzioch_2016_BoostedRegressionTree]] — but a *level* real-yield signal has never been tested. New pre-registration required to try it.
