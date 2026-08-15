---
type: moc
title: "Researcher Vault — Session State"
tags: [type/moc]
---

# Session State — Vault Design (researcher agent)

## Task
Design a complete Obsidian vault for quant_os paper library / edge tracking. DONE.

## What was built (vault root: quant_os/vault/)
- README.md — design + operating manual (7 sections)
- 00_MOC/ — 6 auto-populating MOCs (Hypotheses, Papers, Rejected, Data, Tooling, Experiments)
- Templates/ — 6 TPL files (Paper, Hypothesis, Experiment, Daily, Data, Tool)
- Dataview/QUERIES.md — 14 DQL queries (A–N) answering the 2 key questions
- Integration/Integration_Map.md — vault ↔ research/ + reports/ Rosetta Stone
- Seed notes (12): 4 papers, 3 hypotheses (2 rejected + 1 candidate), 2 experiments, 1 data, 1 tool, 1 daily

## Grounding (read from real repo)
- research/generation_framework.md (7 hypothesis cats)
- research/hypothesis_registry.json (14 trials, ALL rejected)
- research/pre_registration/template.md (trial template reused)
- FOREX_EDGE_INVESTIGATION.md (cost-dominance root cause)
- DEEP_RESEARCH_QUANT_STRATEGIES.md (10-priority tooling)
- research/alternative_gold_data_sources.md (10 data cats)
- research/academic_gold_price_research.md (real papers, evidence ratings)

## Next steps for user
1. Open Obsidian, set vault = quant_os/vault/
2. Enable Dataview + Templater
3. Populate Papers/ from academic_gold_price_research.md (already seeded 4)
4. Run query A (Untested Leads) weekly
5. Keep Integration_Map sync rules (registry = source of truth)
