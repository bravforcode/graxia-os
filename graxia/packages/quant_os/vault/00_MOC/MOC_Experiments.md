# MOC — Experiments

> One log per trial run. Bridges hypothesis → validation pipeline → reports/ evidence artifact.
> External numbers live in `../reports/*.json` — this note stores *judgment* + *link*.

## All Experiments (auto)
```dataview
TABLE verdict, trial_id, gates_passed, gates_failed, date_run
FROM "Experiments"
SORT date_run DESC
```

## By Verdict
```dataview
TABLE hypothesis_ref, gates_passed, gates_failed, root_cause
FROM "Experiments"
FLATTEN verdict
GROUP BY verdict
```

## Linked to a Hypothesis (drill-down)
```dataview
TABLE verdict, evidence_artifact, root_cause
FROM "Experiments"
WHERE contains(linked_hypotheses, this.file.link)
```

## External Evidence Artifacts (reports/)
- [pre_registered_criteria.txt](../reports/pre_registered_criteria.txt) — EURUSD RSI+BB gates
- [pooled_trend_strategies_results.json](../reports/pooled_trend_strategies_results.json)
- [edge_search_cross_sectional_20260720.json](../reports/edge_search_cross_sectional_20260720.json)
- [FOREX_EDGE_INVESTIGATION.md](../FOREX_EDGE_INVESTIGATION.md) — FX cost-dominance root cause
- [hypothesis_registry.json](../research/hypothesis_registry.json) — 14 trials, all rejected

## Quick Jump
- Hypotheses → [[MOC_Hypotheses]] · Rejected → [[MOC_Rejected]] · Papers → [[MOC_Papers]]
