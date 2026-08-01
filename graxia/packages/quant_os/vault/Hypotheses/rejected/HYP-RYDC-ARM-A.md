---
title: "RYDC-ARM-A — Real-Yield Divergence Continuation"
type: hypothesis
status: rejected
category: macro
instrument: [xauusd]
trial_id: "1001"
registry_ref: "research/hypothesis_registry.json"
pre_reg_doc: "research/pre_registration/hypothesis_02_real_yield_divergence.md"
mechanism: "Gold responds to DXY/real-yield with a diffusion lag; trade continuation of the divergence (Arm A: trend-continuation)."
prior_probability: low
dsr_cumulative_at_test: 2001
validation_result: REJECTED
verdict_date: "2026-07-12"
gates: {p_value: 0.968, deflated_sharpe_pct: 0.16, wfe: null, min_trades: 52}
root_cause_if_rejected: "no-gross-edge"
linked_papers: ["[[Paper_Pierdzioch_2016_BoostedRegressionTree]]"]
linked_experiments: ["[[EXP-1001-RYDC]]"]
linked_reports: ["../research/hypothesis_registry.json"]
tags: [type/hypothesis, domain/macro, edge/rejected, status/rejected]
---

# RYDC-ARM-A — Real-Yield Divergence Continuation

## 1. Economic Rationale
Real rates + USD are gold's #1-2 predictors (see [[Paper_Pierdzioch_2016_BoostedRegressionTree]]). Hypothesis: when DXY/real-yield diverges, XAUUSD *follows with a lag*. **But** RYDC found the response is **contemporaneous, no diffusion lag** → the lag tradeable mechanism is null. Prior probability was LOW from the start (p=0.9680 = strong null).

## 2. Arm Selection
| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Continuation** | Divergence persists, trade follow-through | Lag diffusion |
| B — Reversal | Divergence mean-reverts | Overreaction |

**Registered choice: Arm A.** Result: p=0.9680 — coin-flip, strong null.

## 3. Data Requirements
| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD | data/XAUUSD_D1.csv | D1 | 5y+ |
| DXY | data/DXY_D1.csv | D1 | 5y+ |

## 4. Validation Gates
| Gate | Value | Threshold | Status |
|---|---|---|---|
| p-value | 0.968 | < 0.05 | ❌ |
| Deflated Sharpe % | 0.16 | > 0.95 | ❌ |
| Min trades | 52 | ≥ 100 | ❌ |

## 5. Root Cause (the valuable part)
**`no-gross-edge`** — the mechanism itself is wrong (contemporaneous, not lagged). Distinct from cost-dominance (FX) and sample-size (crypto). Lesson: the *predictor* is real; the *tradeable lag* is not.

## 6. Links
- **Paper behind this:** [[Paper_Pierdzioch_2016_BoostedRegressionTree]] (real rates predict — but not with a lag)
- **Experiment:** [[EXP-1001-RYDC]]
- **Registry:** [hypothesis_registry.json](../research/hypothesis_registry.json)
