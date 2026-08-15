---
title: "META-LEARNING — Cross-Asset Few-Shot Strategy Induction"
type: hypothesis
status: candidate
category: ml-forecasting
instrument: [xauusd, btcusd, ethusd]
trial_id: ""
registry_ref: "research/hypothesis_registry.json"
pre_reg_doc: ""
mechanism: "A meta-learned initializer produces asset-specific strategy heads from <50 past trades, mitigating the <100-trade sample-size wall that killed BVC (29 trades) and COT (7 trades). Learns HOW to learn, not a single factor."
prior_probability: low
dsr_cumulative_at_test: 2001
validation_result: ""
verdict_date: ""
gates: {p_value: null, deflated_sharpe_pct: null, wfe: null, min_trades: null}
root_cause_if_rejected: ""
linked_papers: ["[[Paper_Oyedele_2023_Transformer]]"]
linked_experiments: []
linked_reports: ["../research/meta_learning.md"]
tags: [type/hypothesis, domain/ml-forecasting, edge/candidate, status/candidate]
---

# META-LEARNING — Cross-Asset Few-Shot Strategy Induction

> **Status: CANDIDATE** (hunch, not yet pre-registered). Live research direction — see [research/meta_learning.md](../research/meta_learning.md) and [research/meta_learning_c.md](../research/meta_learning_c.md).

## 1. Economic Rationale
The dominant rejection pattern in the registry is **sample-too-small** (BVC 29 trades, COT 7 trades) and **regime-mismatch**. Meta-learning (MAML-style) induces a good strategy prior from *related assets'* history, then adapts to the target with few samples. This directly attacks the <100-trade wall.

## 2. Why structurally different from RYDC
RYDC assumed a *single* macro factor with a lag. This assumes *no single factor* — instead a *learned adaptation function*. Different failure mode; not a re-test of a dead idea.

## 3. Arm Selection (proposed)
| Arm | Prediction | Mechanism |
|---|---|---|
| **A — MAML gold-head** | Fast adapt to XAUUSD from cross-asset prior | Few-shot |
| B — Plain transfer | Fine-tune pretrained on BTC/ETH | Standard TL |

## 4. Data Requirements (future)
| Series | Source | Frequency | Min history |
|---|---|---|---|
| XAUUSD + BTC + ETH | MT5 / ccxt | H1 | 2y each |

## 5. Open Dependencies
- Needs [[Paper_Oyedele_2023_Transformer]] architecture reference.
- Needs `ccxt` (see [[../Tooling/pandas-ta]] sibling list) for crypto history → blocked until [DEEP_RESEARCH_QUANT_STRATEGIES](../DEEP_RESEARCH_QUANT_STRATEGIES.md) Phase 1 lands.
- **Must clear the 7 validation gates + new pre-registration before any backtest.**

## 6. Links
- **Paper behind this:** [[Paper_Oyedele_2023_Transformer]]
- **Live direction:** [meta_learning.md](../research/meta_learning.md)
