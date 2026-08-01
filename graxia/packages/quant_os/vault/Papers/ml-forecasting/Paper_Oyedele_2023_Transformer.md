---
title: "Oyedele et al. (2023) — Deep Learning for Gold: LSTM/GRU/Transformer"
aliases: [oyedele2023]
type: paper
status: to-read
domain: [ml-forecasting]
instrument: [xauusd, btcusd, ethusd]
evidence: medium
source: academic
year: 2023
venue: "arXiv:2312.xxxx"
citekey: oyedele2023
url: "https://arxiv.org/abs/2312.xxxx"
doi: ""
tags: [type/paper, domain/ml-forecasting, status/to-read, evidence/medium, source/academic, priority/p1]
reading_dates: ["2026-07-28"]
key_claim: "Transformers beat LSTM/GRU by ~8% on 20-day horizon; LSTM best for 1-day ahead; GRU best compute/accuracy tradeoff."
quant_os_hook: "Architecture search space for the gold prediction engine; also motivates META-LEARNING (few-shot asset heads) via Transformer inductive bias."
rejected_by: []
applied_to: []
linked_hypotheses: ["[[HYP-META-LEARNING]]"]
linked_experiments: []
related_papers: ["[[Paper_Baur_Lucey_2010_SafeHaven]]"]
---

# Oyedele et al. (2023) — Deep Learning for Gold: LSTM/GRU/Transformer

## 1. Citation
> Oyedele, T. et al. (2023). Deep Learning for Gold Price Prediction: A Comparative Study of LSTM, GRU, and Transformer Models. *arXiv:2312.xxxx* (pre-print).

## 2. Key Claim
- **Mechanism:** Transformer attention captures longer-range dependencies in gold series better than recurrent nets.
- **Prediction:** 20-day horizon → Transformer; 1-day → LSTM.
- **Why persistent:** Architecture choice is a *tooling* edge, not a market inefficiency.

## 3. Method & Evidence Quality
- **Data:** Gold daily, 20-day + 1-day horizons.
- **OOS?** Claimed. **Replicable?** Pre-print, needs peer review.
- **My evidence rating:** MEDIUM — recent, not yet peer-reviewed, but consistent with Sezer (2020) survey.

## 4. quant_os Applicability
- **Maps to:** #domain/ml-forecasting
- **Concrete hypothesis:** Feeds [[HYP-META-LEARNING]] — a Transformer-based meta-learner could induce asset-specific heads from <50 trades, bypassing the <100-trade wall that killed BVC (29 trades) and COT (7 trades).
- **Untensted lead:** No experiment has tested Transformer architectures or meta-learning yet → surfaces in Dataview query A (untested leads).

## 5. Notes / Critique
- Caveat: DL on <5y data overfits (Henrique 2019 warns). quant_os has 12.99y for some assets but only ~weeks for crypto.

## 6. Links
- Hypothesis spawned: [[HYP-META-LEARNING]]
- Sibling survey: [[Paper_Sezer_2020_DLSLR]] (if created)
