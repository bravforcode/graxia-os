# MOC — Rejected (Negative Results)

> **THE most valuable view in the vault.** This is the graveyard of every edge we tested and killed.
> Purpose: (1) never silently re-test a dead idea; (2) see the *pattern* of death (cost? sample size? regime?); (3) find the *adjacent* untested corner.
> Feeds the question: *"What papers could give an edge we haven't tried?"* → if a paper's idea is HERE, skip or pivot; if it's NOT here, it's a lead.

## Rejected Hypotheses (auto)
```dataview
TABLE category, instrument, trial_id, root_cause_if_rejected, verdict_date
FROM "Hypotheses"
WHERE status = "rejected" OR validation_result = "REJECTED"
SORT verdict_date DESC
```

## Root-Cause Rollup (where do edges die?)
```dataview
TABLE length(rows) AS count
FROM "Hypotheses"
WHERE status = "rejected"
FLATTEN root_cause_if_rejected
GROUP BY root_cause_if_rejected
```

## Experiments that Rejected (with verdict)
```dataview
TABLE verdict, gates_passed, gates_failed, root_cause, evidence_artifact
FROM "Experiments"
WHERE verdict = "REJECTED" OR verdict = "INSUFFICIENT_DATA"
SORT date_run DESC
```

## Papers whose Mechanism was Killed
```dataview
TABLE rejected_by
FROM "Papers"
WHERE length(rejected_by) > 0
```

## The 14 Dead-End Trials (ground truth from research/hypothesis_registry.json)
| Trial | ID | Mechanism | Verdict | Root cause to record |
|---|---|---|---|---|
| 1001 | RYDC-ARM-A | Real-yield divergence continuation | REJECTED p=0.968 | contemporaneous response, no lag |
| 1003 | CAM-DXY-XAUUSD | DXY→XAUUSD diffusion lag | REJECTED p=0.598 | diffusion-lag null |
| 1004 | SP-SESSION-CONDITIONAL | Session vol clustering | REJECTED p=0.934 | coin-flip |
| 1005 | MRM-REGIME-CONDITIONAL | Regime-conditional MR | REJECTED Sharpe -1.16 | regime-mismatch |
| 1006 | GSS-GOLD-SILVER-SPREAD | Gold/Silver ratio MR | REJECTED Sharpe -0.96 | <100 trades |
| 1007 | BVC-BTC-VOL-CLUSTERING | BTC vol spike continuation | REJECTED (29 trades) | sample-too-small |
| 1008 | CVR-CROSS-ASSET-VOL-RANK | Cross-asset vol rank | REJECTED Sharpe -0.40 | negative sharpe |
| 1022 | MULTI-ASSET-TSMOM-RANKING | TSMOM + ranking | REJECTED dk_t -2.13 | no edge across assets |
| 1023 | ETH-VOL-CONFIRM | ETH volume confirmation | REJECTED Sharpe -1.36 | negative |
| 1024 | BTC-ETH-VOL-SPREAD | BTC-ETH vol spread | INSUFFICIENT_DATA | 0 trades |
| 1025 | COT-POSITIONING | COT positioning | REJECTED (7 trades) | sample-too-small |
| 1026 | FOMC-DRIFT | FOMC drift | REJECTED Sharpe -0.68 | negative |
| 1027 | FUNDING-RATE-ARB | Funding rate arb | REJECTED (0 trades) | missing-stop-loss bug |

> Source of truth: [hypothesis_registry.json](../research/hypothesis_registry.json) · see also [FOREX_EDGE_INVESTIGATION](../FOREX_EDGE_INVESTIGATION.md) for the *cost-dominance* root cause that kills FX.

## Quick Jump
- Hypotheses → [[MOC_Hypotheses]] · Papers → [[MOC_Papers]] · Experiments → [[MOC_Experiments]]
