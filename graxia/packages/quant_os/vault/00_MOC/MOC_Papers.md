# MOC — Papers

> The library index. Filter by domain, evidence, or reading status.
> **Use this to triage the to-read queue** and to see *which papers we've already mined*.

## All Papers by Evidence (auto)
```dataview
TABLE evidence, status, source, year
FROM "Papers"
SORT evidence ASC, year DESC
```

## To-Read Queue (unread, ranked)
```dataview
TABLE evidence, domain, priority
FROM "Papers"
WHERE status = "to-read"
SORT evidence ASC, file.ctime DESC
```

## Already Applied (don't re-mine)
```dataview
LIST FROM "Papers"
WHERE status = "applied" OR length(applied_to) > 0
```

## By Domain (click a corner we haven't covered)
```dataview
TABLE status, evidence
FROM "Papers"
FLATTEN domain
GROUP BY domain
```

## Rejected Ideas (paper's mechanism already killed)
```dataview
LIST rejected_by
FROM "Papers"
WHERE length(rejected_by) > 0
```

## Domain Subfolders
- [[../Papers/ml-forecasting/]] · [[../Papers/safe-haven/]] · [[../Papers/macro/]]
- [[../Papers/microstructure/]] · [[../Papers/sentiment/]] · [[../Papers/volatility/]] · [[../Papers/crypto/]]

## Quick Jump
- Hypotheses → [[MOC_Hypotheses]] · Rejected → [[MOC_Rejected]]
- Experiments → [[MOC_Experiments]] · Data → [[MOC_Data]] · Tooling → [[MOC_Tooling]]
