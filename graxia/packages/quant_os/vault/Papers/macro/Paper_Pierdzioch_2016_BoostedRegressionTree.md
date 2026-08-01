---
title: "Pierdzioch et al. (2016) — Boosted Regression Tree Gold Forecasting"
aliases: [pierdzioch2016]
type: paper
status: synthesis
domain: [macro]
instrument: [xauusd]
evidence: high
source: academic
year: 2016
venue: "Resources Policy"
citekey: pierdzioch2016
url: ""
doi: ""
tags: [type/paper, domain/macro, status/synthesis, evidence/high, source/academic]
reading_dates: ["2026-07-25"]
key_claim: "Top-5 gold predictors: (1) USD exchange rate, (2) Real interest rates, (3) Inflation expectations, (4) VIX, (5) Oil. Boosting > Random Forest."
quant_os_hook: "Feature selection for gold model: rank by SHAP/XGBoost; real rates + USD are dominant. Informs why RYDC's real-yield mechanism is plausible but its LAG assumption was wrong."
rejected_by: ["1001"]
applied_to: []
linked_hypotheses: ["[[HYP-RYDC-ARM-A]]"]
linked_experiments: ["[[EXP-1001-RYDC]]"]
related_papers: ["[[Paper_Shahbaz_2020_EPU]]"]
---

# Pierdzioch et al. (2016) — Boosted Regression Tree Gold Forecasting

## 1. Citation
> Pierdzioch, C., Risse, M., & Roth, S. (2016). Forecasting Gold Price Fluctuations: A Boosted Regression Tree Approach. *Resources Policy*.

## 2. Key Claim
- **Mechanism:** Real interest rates + USD dominate gold's predictable component; boosting captures non-linearities better than RF.
- **Prediction:** A real-rate + USD feature set should rank #1-2 in any gold model.
- **Why persistent:** Macro fundamentals are slow-moving structural forces.

## 3. Method & Evidence Quality
- **Data:** Macro panel, rigorous feature-importance methodology.
- **OOS?** Yes. **Replicable?** Yes.
- **My evidence rating:** HIGH — directly validates quant_os's existing real-yield focus.

## 4. quant_os Applicability
- **Maps to:** #domain/macro
- **The crux:** This paper says real rates *predict* gold. RYDC (trial 1001) tested a *specific* mechanism — a **diffusion lag** where DXY/real-yield extremes *lead* XAUUSD. RYDC was **REJECTED (p=0.968)** — conclusion: "Gold response to DXY/real-yield is **contemporaneous, no diffusion lag**." So the predictor is real, but the *lag* tradeable mechanism is null. → `rejected_by: [1001]`.

## 5. Notes / Critique
- Don't re-test "real rates predict gold" — that's not the edge. The open question is *how to trade the contemporaneous relationship* (level, not lag). No trial has tried a *level* real-yield signal yet.

## 6. Links
- Hypothesis that tested its mechanism: [[HYP-RYDC-ARM-A]]
- Experiment that killed the lag variant: [[EXP-1001-RYDC]]
- Sibling (another macro driver): [[Paper_Shahbaz_2020_EPU]]
