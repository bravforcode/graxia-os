# Dataview Query Library

> Paste any block into a note (or the Dataview query block). All assume the frontmatter schemas in `Templates/`.
> Two meta-questions answered:
> **Q1 "What papers could give an edge we haven't tried?"** → queries **A, B, G, H**.
> **Q2 "Track read / applied / rejected?"** → queries **C, D, E, F, I**.

---

## A. UNTESTED LEADS — papers whose idea we've never killed
```dataview
TABLE evidence AS Ev, domain AS Dom, source AS Src, year AS Yr
FROM "Papers"
WHERE status != "applied"
  AND status != "rejected"
  AND (rejected_by = null OR length(rejected_by) = 0)
SORT evidence ASC, file.ctime DESC
```
> Reads as: "papers we've logged but whose mechanism no experiment has rejected." These are live ore.

## B. HIGH-VALUE UNTESTED — the real edge candidates
```dataview
TABLE evidence AS Ev, domain AS Dom, priority AS Pri
FROM "Papers"
WHERE status = "to-read"
  AND evidence = "high"
SORT file.ctime DESC
```
> Pair with `priority/p0` tag if you triage by effort too.

## C. READ vs APPLIED vs REJECTED — the lifecycle pivot (answers Q2)
```dataview
TABLE
  length(filter(status, (s) => s = "applied")) > 0 ? "applied" :
  length(rejected_by) > 0 ? "rejected" :
  status AS "reading-status"
FROM "Papers"
GROUP BY choice
```
> Simpler split (status field already encodes to-read/reading/synthesis/applied/rejected):
```dataview
TABLE status, evidence, length(applied_to) AS "#applied", length(rejected_by) AS "#rejected-by"
FROM "Papers"
SORT status ASC
```

## D. PAPERS WE'VE READ BUT NOT YET APPLIED
```dataview
LIST FROM "Papers"
WHERE status IN ["reading","synthesis"]
  AND (applied_to = null OR length(applied_to) = 0)
```

## E. NEGATIVE RESULTS — papers whose mechanism was killed (rejected_by)
```dataview
TABLE rejected_by AS "killed-by-trial"
FROM "Papers"
WHERE length(rejected_by) > 0
SORT length(rejected_by) DESC
```
> This is the anti-recommendation list: don't re-mine these mechanisms without a structural change.

## F. HYPOTHESES BY STATUS (the pipeline)
```dataview
TABLE category, instrument, validation_result, verdict_date
FROM "Hypotheses"
SORT status DESC
```

## G. GAP FINDER — domains with fewest papers (edge hides in thin coverage)
```dataview
TABLE length(rows) AS "#papers"
FROM "Papers"
FLATTEN domain
GROUP BY domain
SORT length(rows) ASC
```
> The bottom of this list = research areas you've under-explored. Each is a candidate for "what haven't we tried."

## H. REJECTED EXPERIMENTS + ROOT CAUSE (pattern of death)
```dataview
TABLE root_cause, gates_passed, gates_failed, metrics.n_trades AS trades
FROM "Experiments"
WHERE verdict = "REJECTED" OR verdict = "INSUFFICIENT_DATA"
SORT date_run DESC
```

## I. REJECTED HYPOTHESES — full graveyard
```dataview
TABLE trial_id, root_cause_if_rejected, verdict_date, linked_papers
FROM "Hypotheses"
WHERE status = "rejected"
SORT verdict_date DESC
```

## J. DATA SOURCES MISSING BUT HIGH-RELEVANCE (unblock a dead hypothesis)
```dataview
LIST gold_relevance, cost, quant_os_integration
FROM "Data"
WHERE gold_relevance = "high" AND status = "missing"
SORT priority_rank ASC
```

## K. TOOLS NOT YET ADOPTED (ranked)
```dataview
TABLE category, value, effort, quant_os_use
FROM "Tooling"
WHERE status = "not-used"
SORT priority_rank ASC
```

## L. DAILY RESEARCH ROLLUP — last 14 days
```dataview
TABLE papers_read, hypotheses_advanced, experiments_run, open_questions, edge_leads
FROM "Daily"
WHERE file.day >= date(today) - dur(14 days)
SORT file.day DESC
```

## M. CROSS-LINK INTEGRITY — hypotheses with NO paper (hunches, not research)
```dataview
LIST FROM "Hypotheses"
WHERE length(linked_papers) = 0
```
> Any hit here violates the linking rule → either link a paper or move to `candidates/`.

## N. COST-DOMINANCE FILTER — FX edges we should NOT revisit
```dataview
LIST FROM "Experiments"
WHERE contains(root_cause, "cost") OR cost_model = "pepperstone_razor"
```
> Mirrors [FOREX_EDGE_INVESTIGATION](../FOREX_EDGE_INVESTIGATION.md): $7/rt commission eats 15–23% of FX moves.
