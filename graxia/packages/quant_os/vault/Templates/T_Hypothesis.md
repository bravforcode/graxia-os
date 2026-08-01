---
title: "{{HYP-NAME}}"
type: hypothesis
status: candidate           # candidate | pre-registered | testing | passed | rejected | applied
category: macro-regime      # one of 7 framework cats OR cross-sectional-momentum|crypto-single-asset|crypto-relative-value|macro-positioning|event-driven|crypto-funding
instrument: [xauusd]     # xauusd|xagusd|btcusd|ethusd|fx-major|multi-asset
trial_id: ""               # e.g. 1003 / RYDC-ARM-A — leave blank until pre-registered
registry_ref: "research/hypothesis_registry.json"
pre_reg_doc: ""            # research/pre_registration/trial_XXXX.md once locked
mechanism: "{{named behavioral/structural cause — NOT 'indicator X predicts Y'}}"
prior_probability: low     # all NEW hypotheses have LOW prior (RYDC Arm A p=0.9680 — strong null)
dsr_cumulative_at_test: 2001   # from research/trial_ledger.json at lock time
validation_result: ""     # PASSED | REJECTED | INSUFFICIENT_DATA
verdict_date: ""
gates: {p_value: null, deflated_sharpe_pct: null, wfe: null, min_trades: null}
root_cause_if_rejected: ""  # cost-dominance|feature-mismatch|no-gross-edge|sample-too-small|regime-mismatch|already-tested
linked_papers: []          # [[Paper: ...]] — REQUIRED: ≥1, or downgrade to candidate
linked_experiments: []     # [[EXP-...]] — the trial run(s)
linked_reports: []         # ../reports/... external links
tags: [type/hypothesis, domain/macro-regime, edge/candidate, status/candidate]
---

# {{HYP-NAME}}

## 1. Economic Rationale
{{Named falsifiable mechanism. What force exists in 2026 markets and is NOT arbitraged instantly?
 Must differ structurally from RYDC (real-yield divergence) — that returned p=0.9680.}}

## 2. Arm Selection (ONE arm, picked before testing)
| Arm | Prediction | Mechanism |
|---|---|---|
| **A — {{name}}** | {{pred}} | {{why}} |
| B — {{name}} | {{pred}} | {{why}} |

**Registered choice: Arm {{A/B}}.** Testing both = PBO=0.50 failure mode.

## 3. Data Requirements
| Series | Source | Frequency | Min history |
|---|---|---|---|
| {{instrument}} | {{source}} | {{freq}} | {{years, span 2+ regimes}} |

## 4. Feature Construction (frozen pseudocode)
```
signal_t = f(data_{t-1}, params)   # coefficients estimated through t-1 only
```

## 5. Validation Gates (identical to pipeline — no relaxation)
| Gate | Threshold | Value | Status |
|---|---|---|---|
| p-value | < 0.05 | | |
| WFA OOS positive | ≥ 70% | | |
| WFE | ≥ 0.5 & < 1.5 | | |
| Deflated Sharpe | > 0.95 (cumulative trials) | | |
| Bootstrap CI | excludes 0 | | |
| Min trades | ≥ 100 | | |

## 6. Links
- **Papers behind this:** {{[[Paper: ...]]}}
- **Experiments:** {{[[EXP-...]]}}
- **External pre-reg:** [{{pre_reg_doc}}](../{{pre_reg_doc}})
- **Registry:** [hypothesis_registry.json](../research/hypothesis_registry.json)
