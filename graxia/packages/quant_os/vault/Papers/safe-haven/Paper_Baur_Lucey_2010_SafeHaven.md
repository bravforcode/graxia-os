---
title: "Baur & Lucey (2010) — Is Gold a Hedge or Safe Haven?"
aliases: [baur2010, Baur & Lucey 2010]
type: paper
status: synthesis
domain: [safe-haven]
instrument: [xauusd]
evidence: high
source: academic
year: 2010
venue: "Financial Review, 45(2), 217-229"
citekey: baur2010
url: ""
doi: ""
tags: [type/paper, domain/safe-haven, status/synthesis, evidence/high, source/academic]
reading_dates: ["2026-07-25"]
key_claim: "Gold hedges stocks on average but is a SAFE HAVEN only in extreme 1% tail equity events; NOT a safe haven for bonds. Window length is critical."
quant_os_hook: "Define safe-haven regime as equity returns < 5th percentile; use as regime-switch trigger for MRM-style strategies."
rejected_by: []
applied_to: ["Hypotheses/rejected/HYP-MRM-REGIME-CONDITIONAL.md"]
linked_hypotheses: ["[[HYP-MRM-REGIME-CONDITIONAL]]"]
linked_experiments: ["[[EXP-1005-MRM]]"]
related_papers: []
---

# Baur & Lucey (2010) — Is Gold a Hedge or Safe Haven?

## 1. Citation
> Baur, D. G., & Lucey, B. M. (2010). Is Gold a Hedge or a Safe Haven? An Analysis of Stocks, Bonds and Gold. *Financial Review*, 45(2), 217-229.

## 2. Key Claim
- **Mechanism:** Gold's safe-haven property is *state-dependent* — it appears only when equities crash (1% tail), not continuously.
- **Prediction:** Gold-equity correlation turns strongly negative exactly in tail events; near-zero otherwise.
- **Why persistent:** Behavioral flight-to-safety is structural, not arbitraged.

## 3. Method & Evidence Quality
- **Data:** Stocks, bonds, gold, multi-country, long history.
- **OOS?** GARCH-based methodology, robust.
- **Replicable?** Yes, foundational (2,500+ citations).
- **My evidence rating:** HIGH — rigorous GARCH, extreme tail focus directly maps to quant_os regime detection.

## 4. quant_os Applicability
- **Maps to:** #domain/safe-haven
- **Concrete hypothesis:** Use equity-return-5th-percentile as a *regime switch* that flips MR↔momentum. This is exactly what MRM (trial 1005) tried — and MRM **failed** (see [[EXP-1005-MRM]]), but MRM used *real-yield CV*, not *equity-tail* as the trigger. The paper suggests the trigger choice may be the bug.

## 5. Notes / Critique
- MRM-REGIME-CONDITIONAL rejected with Sharpe -1.16. Root cause logged as `regime-mismatch`. Per this paper, the *equity-tail* definition of regime may work where *real-yield-CV* did not. → candidate for re-test with different regime classifier (would need NEW pre-registration).

## 6. Links
- Hypotheses spawned: [[HYP-MRM-REGIME-CONDITIONAL]]
- Experiments that tested adjacent idea: [[EXP-1005-MRM]]
