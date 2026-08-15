---
title: "EXP-{{trial_id}} {{name}}"
type: experiment
status: done                 # planned | running | done
hypothesis_ref: ""        # "[[HYP-...]]" — REQUIRED backward link
trial_id: ""              # 1003 / RYDC-ARM-A
registry_ref: "research/hypothesis_registry.json"
runner: "scripts/run_strategy_validation.py"
data_sources: []          # [data/XAUUSD_D1.csv, data/DXY_D1.csv]
date_run: ""
verdict: REJECTED          # PASSED | REJECTED | INSUFFICIENT_DATA
gates_passed: 0
gates_failed: 0
metrics: {p_value: null, sharpe: null, wfe: null, n_trades: null, deflated_sharpe_pct: null}
evidence_artifact: ""     # ../reports/...json — authoritative numbers live here
root_cause: ""            # diffusion-lag-null|cost-dominance|feature-mismatch|sample-too-small|regime-mismatch
cost_model: pepperstone_razor
tags: [type/experiment, domain/macro-regime, edge/rejected, status/done, instrument/xauusd]
---

# EXP-{{trial_id}} {{name}}

## 1. Hypothesis Under Test
→ [[{{HYP-...}}]]

## 2. Setup
- **Runner:** `{{runner}}`
- **Data:** {{data_sources}}
- **Cost model:** {{cost_model}} ($7/rt FX commission is the structural headwind — see [FOREX_EDGE_INVESTIGATION](../FOREX_EDGE_INVESTIGATION.md))

## 3. Results (from {{evidence_artifact}})
| Gate | Value | Threshold | Pass? |
|---|---|---|---|
| p-value | {{}} | < 0.05 | |
| WFA OOS+ | {{}} | ≥ 70% | |
| WFE | {{}} | ≥ 0.5 | |
| Deflated Sharpe % | {{}} | > 0.95 | |
| Min trades | {{}} | ≥ 100 | |

**Verdict:** {{verdict}} — gates passed {{gates_passed}} / failed {{gates_failed}}.

## 4. Root Cause (the valuable part)
{{Why did this die? Tie to FOREX_EDGE_INVESTIGATION root causes if applicable.
 e.g. "Model has gross edge (gross PnL +$23,714) but $7/rt commission → net -$1.42."}}

## 5. External Evidence
- [{{evidence_artifact}}](../{{evidence_artifact}})
- [registry entry](../research/hypothesis_registry.json)

## 6. Follow-up
- {{what would need to change to retest legitimately (new pre-registration required)}}
