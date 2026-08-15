---
title: "{{title}}"
aliases: [{{citekey}}, {{short_title}}]
type: paper
status: to-read            # to-read | reading | synthesis | applied | rejected | archived
domain: [ml-forecasting]   # cross-asset-momentum|vol-risk-premium|session-pattern|orderflow|macro-regime|carry-momentum|mean-reversion|ml-forecasting|safe-haven|microstructure|sentiment|volatility|crypto|macro
instrument: [xauusd]     # xauusd|xagusd|btcusd|ethusd|fx-major|multi-asset
evidence: medium           # high | medium | low  (applicability / quality of finding)
source: academic           # academic | blog | book | internal-report | vendor-doc
year: {{year}}
venue: "{{journal}}"
citekey: {{citekey}}
url: {{url}}
doi: {{doi}}
tags: [type/paper, domain/ml-forecasting, status/to-read, evidence/medium, source/academic]
reading_dates: []          # auto-filled from Daily notes
key_claim: "{{one-sentence mechanism the paper asserts}}"
quant_os_hook: "{{which feature / regime / signal in quant_os this could inform}}"
rejected_by: []            # trial_ids that tested this idea and FAILED → links to Experiments/
applied_to: []            # strategy files or trial_ids that successfully used it
linked_hypotheses: []     # [[HYP-...]] notes this paper spawned
linked_experiments: []      # [[EXP-...]] notes that tested it
related_papers: []         # [[Paper: ...]] siblings / contradictions
---

# {{title}}

## 1. Citation
> {{full APA or BibTeX citation}}

## 2. Key Claim (their words, my paraphrase)
- **Mechanism:** {{what economic/structural force do they claim produces the predicted return?}}
- **Prediction:** {{what exactly should happen, on what horizon?}}
- **Why persistent:** {{why wouldn't this be arbitraged away by 2026?}}

## 3. Method & Evidence Quality
- **Data:** {{sample, frequency, span, asset}}
- **Out-of-sample?** {{yes/no, how}}
- **Replicable?** {{code repo? dataset public?}}
- **My evidence rating:** {{high|medium|low}} — {{justification: journal tier, n, OOS, replicability}}

## 4. quant_os Applicability
- **Maps to domain:** #domain/{{...}}
- **Concrete feature/hypothesis it suggests:** {{e.g. "add DFII5 to macro regime classifier"}}
- **Conflicts with existing rejected work?** {{link to [[EXP-...]] or [[HYP-...]] if so}}

## 5. Notes / Critique
- {{my running thoughts, limitations, overfitting risks}}

## 6. Links
- Papers: {{[[Paper: sibling]]}}
- Hypotheses spawned: {{[[HYP-...]]}}
- Experiments that tested it: {{[[EXP-...]]}}
