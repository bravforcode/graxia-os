# MOC — Hypotheses

> Every hypothesis, colored by lifecycle. The pipeline at a glance.
> **Read this first** when asking *"what haven't we tried?"* → jump to `MOC_Rejected` for the graveyard, then scan `candidates/` for live ore.

## By Lifecycle (auto)
```dataview
LIST status, category, trial_id
FROM "Hypotheses"
SORT status DESC
```

## Subfolders (manual entry)
- [[../Hypotheses/candidates/]] — ideas not yet pre-registered (hunches only)
- [[../Hypotheses/pre-registered/]] — locked, awaiting / under test
- [[../Hypotheses/rejected/]] — dead ends + root cause (the valuable pile)

## By Category (7 framework cats + extensions)
```dataview
TABLE status, instrument, validation_result
FROM "Hypotheses"
WHERE type = "hypothesis"
FLATTEN domain
GROUP BY category
```

## Live Pipeline (non-rejected only)
```dataview
LIST FROM "Hypotheses"
WHERE status IN ["candidate","pre-registered","testing","passed"]
SORT file.ctime ASC
```

## Quick Jump
- Back to [[README]]
- Papers index → [[MOC_Papers]]
- Negative results → [[MOC_Rejected]]
- Experiments ↔ reports → [[MOC_Experiments]]
- Data sources → [[MOC_Data]]
- Tooling → [[MOC_Tooling]]
