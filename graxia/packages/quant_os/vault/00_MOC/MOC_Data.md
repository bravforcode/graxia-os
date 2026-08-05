# MOC — Data Sources

> Alternative / missing data for gold (XAUUSD) prediction. Source: [alternative_gold_data_sources.md](../research/alternative_gold_data_sources.md).
> A missing data source is often the *reason* a hypothesis died (e.g. COT died at 7 trades → need better positioning data). Track what to wire in.

## All Data Sources (auto)
```dataview
TABLE category, gold_relevance, cost, update_freq, status
FROM "Data"
SORT gold_relevance ASC, status ASC
```

## Missing but High-Relevance (build next)
```dataview
LIST FROM "Data"
WHERE gold_relevance = "high" AND status = "missing"
SORT priority_rank ASC
```

## By Category
```dataview
TABLE status, cost
FROM "Data"
GROUP BY category
```

## High-Priority Missing (from the source report)
- DFII5 / DFII30 (TIPS 5Y/30Y real yield) — `status: missing`
- USEPUINDXD (Economic Policy Uncertainty) — `status: missing`
- DTWEXAFEGS (advanced trade-weighted USD) — `status: missing`
- GPR Index (geopolitical risk, free CSV) — `status: missing`
- Gold ETF flows (GLD/IAU shares outstanding) — `status: missing`
- Silver COT (duplicate gold pipeline) — `status: missing`
- SGE premium (Shanghai Gold Exchange) — `status: missing`

## Quick Jump
- Hypotheses → [[MOC_Hypotheses]] · Tooling → [[MOC_Tooling]] · README → [[README]]
