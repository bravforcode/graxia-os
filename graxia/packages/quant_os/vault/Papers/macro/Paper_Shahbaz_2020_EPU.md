---
title: "Shahbaz et al. (2020) — Global Economic Policy Uncertainty & Gold"
aliases: [shahbaz2020]
type: paper
status: to-read
domain: [macro, sentiment]
instrument: [xauusd]
evidence: high
source: academic
year: 2020
venue: "Resources Policy"
citekey: shahbaz2020
url: ""
doi: ""
tags: [type/paper, domain/macro, domain/sentiment, status/to-read, evidence/high, source/academic, priority/p0]
reading_dates: ["2026-07-28"]
key_claim: "EPU index Granger-causes gold in 7/10 countries; effect stronger during crises."
quant_os_hook: "Add EPU + GPR indices as features. NO trial has tested sentiment/macro-uncertainty yet — this is a clean UNTESTED lead."
rejected_by: []
applied_to: []
linked_hypotheses: []
linked_experiments: []
related_papers: ["[[Paper_Pierdzioch_2016_BoostedRegressionTree]]"]
---

# Shahbaz et al. (2020) — Global Economic Policy Uncertainty & Gold

## 1. Citation
> Shahbaz, M. et al. (2020). The Impact of Global Economic Policy Uncertainty on Gold Prices. *Resources Policy*.

## 2. Key Claim
- **Mechanism:** Policy uncertainty → safe-haven demand for gold; Granger-causal, not just correlated.
- **Prediction:** Rising EPU leads gold *up*, especially in crises.
- **Why persistent:** Policy uncertainty is a slow, structural macro force.

## 3. Method & Evidence Quality
- **Data:** 10 countries, Granger causality tests.
- **OOS?** Causality framework. **Replicable?** Yes.
- **My evidence rating:** HIGH — clean causal claim, free data (FRED USEPUINDXD, policyuncertainty.com).

## 4. quant_os Applicability
- **Maps to:** #domain/macro, #domain/sentiment
- **UNTESTED LEAD:** The 14 rejected trials covered real-yield, cross-asset momentum, session, regime-MR, gold/silver, vol, COT, FOMC, funding — **NONE tested sentiment/uncertainty**. EPU + GPR are free and directly actionable.
- **Blocker:** EPU FRED series `USEPUINDXD` is in `alternative_gold_data_sources.md` §7 as *missing*. Must wire in first (see [[../Data/DFII5_RealYield]] pattern).

## 5. Notes / Critique
- Granger-causality ≠ tradable edge, but it's a stronger prior than the dead-end factors. Prime candidate for a NEW pre-registration once data is in.

## 6. Links
- Sibling macro driver: [[Paper_Pierdzioch_2016_BoostedRegressionTree]]
- Daily note that flagged it: [[../Daily/2026-07-28]]
