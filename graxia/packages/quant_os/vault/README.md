# QUANT_OS RESEARCH VAULT — Design & Operating Manual

> **Purpose:** A personal quant *paper library + edge-tracking system* for `quant_os` (XAUUSD on MT5 / Pepperstone). Every note exists to answer two questions:
> 1. **"What quant research papers could give us an edge we haven't tried yet?"**
> 2. **"How do we systematically track which papers we've read, applied, and rejected?"**
>
> **Phase context:** quant_os is at Phase 3.1 IN PROGRESS. All 14 pre-registered hypothesis trials (RYDC, CAM, SP, MRM, GSS, BVC, CVR, MULTI-ASSET-TSMOM, ETH-VOL, BTC-ETH, COT, FOMC, FUNDING, …) are **REJECTED / INSUFFICIENT_DATA**. No edge found yet. This vault is the *external memory* that prevents re-reading the same dead-end paper and surfaces the *untested* corner.

---

## 1. Folder Structure (exact)

```
vault/                              ← Obsidian root (lives inside quant_os/)
├── README.md                       ← this file (design + operating manual)
├── 00_MOC/                        ← Maps of Content (entry points, all linked)
│   ├── MOC_Hypotheses.md          ← every hypothesis, colored by status
│   ├── MOC_Papers.md              ← library index, filterable by domain/evidence
│   ├── MOC_Rejected.md           ← NEGATIVE RESULTS — the most valuable view
│   ├── MOC_Data.md               ← alt data sources, ranked by priority
│   ├── MOC_Tooling.md            ← Python libs quant_os doesn't yet use
│   └── MOC_Experiments.md        ← trial runs ↔ registry ↔ reports
├── Templates/                     ← Obsidian template files (TPL plugin / core templates)
│   ├── T_Paper.md
│   ├── T_Hypothesis.md
│   ├── T_Experiment.md
│   ├── T_Data.md
│   ├── T_Tool.md
│   └── T_Daily.md
├── Papers/                        ← one note per paper/book/blog/post
│   ├── ml-forecasting/           ← subfolders mirror #domain tags
│   ├── safe-haven/
│   ├── macro/
│   ├── microstructure/
│   ├── sentiment/
│   ├── volatility/
│   └── crypto/
├── Hypotheses/                   ← mirrors research/pre_registration/
│   ├── candidates/               ← ideas not yet pre-registered
│   ├── pre-registered/          ← locked, awaiting/under test
│   └── rejected/                ← dead ends + root-cause
├── Experiments/                  ← one log per trial run
├── Data/                         ← alt-data source notes (from alternative_gold_data_sources.md)
├── Tooling/                      ← library notes (from DEEP_RESEARCH_QUANT_STRATEGIES.md)
├── Daily/                        ← YYYY-MM-DD.md research journal
├── Dataview/                    ← QUERIES.md (all DQL below) + dashboards
└── Integration/                  ← Integration_Map.md: vault ↔ research/ + reports/
```

**Design rules:**
- **One note = one paper / one hypothesis / one experiment.** No mega-notes. Keeps Dataview queries fast and links clean.
- **Subfolders in `Papers/` mirror `#domain/` tags** — folder for physical browsing, tags for querying. Both must agree.
- **`Hypotheses/` subfolders mirror `status`** so you can see the pipeline at a glance in file explorer.
- **Everything links out** to the real `../research/` and `../reports/` artifacts (relative markdown links), so the vault never duplicates data — it *indexes* it.

---

## 2. Tag Hierarchy (the query backbone)

Tags are the only enforced taxonomy. Frontmatter fields carry the rest. Use the **hierarchical** form `parent/child` so Dataview can pivot on either level.

| Prefix | Children | Meaning |
|---------|-----------|----------|
| `#type/` | `paper`, `hypothesis`, `experiment`, `data`, `tool`, `concept`, `moc`, `daily` | What kind of note |
| `#status/` | `to-read`, `reading`, `synthesis`, `applied`, `rejected`, `archived` | Reading/adoption lifecycle of a paper |
| `#edge/` | `candidate`, `testing`, `found`, `rejected`, `untested`, `insufficient-data` | Edge-finding status of a hypothesis/experiment |
| `#domain/` | `cross-asset-momentum`, `vol-risk-premium`, `session-pattern`, `orderflow`, `macro-regime`, `carry-momentum`, `mean-reversion`, `ml-forecasting`, `safe-haven`, `microstructure`, `sentiment`, `volatility`, `crypto`, `macro` | Research area (7 framework cats + extensions) |
| `#instrument/` | `xauusd`, `xagusd`, `btcusd`, `ethusd`, `fx-major`, `multi-asset` | What it trades |
| `#evidence/` | `high`, `medium`, `low`, `rejected-negative` | Quality / applicability of finding |
| `#source/` | `academic`, `blog`, `book`, `internal-report`, `vendor-doc` | Provenance |
| `#priority/` | `p0`, `p1`, `p2`, `p3` | Triage rank for to-read / to-build |

**Always** set `#type/` + `#status/` + `#domain/` + `#evidence/` (or `#edge/`). Dataview queries below assume these exist.

---

## 3. Linking Strategy (paper → hypothesis → experiment → result)

This is the core. A trading edge is a *chain*: a **paper** proposes a mechanism → a **hypothesis** encodes it as a pre-registered, testable claim → an **experiment** runs the validation pipeline → a **result/report** records pass/reject. Links flow forward and backward:

```
[[Paper: Baur & Lucey 2010 — Safe Haven]]
        │  "mechanism: gold safe-haven only in 1% tail"
        ▼  linked_papers:
[[HYP-MRM-REGIME-CONDITIONAL]]   (hypothesis that tried to use it)
        │  trial_id: 1005
        ▼  linked_experiments:
[[EXP-1005-MRM]]                (experiment log)
        │  verdict: REJECTED, root_cause: regime-mismatch
        ▼  evidence_artifact:
../reports/pooled_trend_strategies_results.json   (external link)
```

**Hard rules:**
1. **Every hypothesis note links ≥1 paper** (`linked_papers:`) and ≥1 experiment (`linked_experiments:`). If a hypothesis has no paper, it's a hunch, not research — downgrade to `#status/candidate` in `Hypotheses/candidates/`.
2. **Every experiment links its hypothesis** (`hypothesis_ref: "[[...]]"`) and its external evidence artifact (`evidence_artifact: "../reports/..."`).
3. **Rejected experiments back-link to the papers they killed** — set `rejected_by: [trial_id]` on the paper note. This is how you answer *"have we tried this paper's idea?"* → if `rejected_by` is non-empty, YES, and here's why it died.
4. **Use `[[wikilinks]]` for in-vault targets, `[relative](../research/foo.md)` for the real quant_os artifacts.** Obsidian renders the latter as external links that open the source file.
5. **`MOC_Rejected.md` is the canonical "negative results" dashboard** — it aggregates every note with `#edge/rejected` or non-empty `rejected_by`, so the graveyard is one click away and never silently re-tested.

---

## 4. Metadata Schema (frontmatter per type)

Full schemas are in `Templates/`. Summary of required fields:

- **Paper:** `title, type, status, domain[], instrument[], evidence, source, year, citekey, key_claim, rejected_by[], applied_to[], related_papers[], related_hypotheses[], related_experiments[]`
- **Hypothesis:** `title, type, status, category, instrument[], trial_id, registry_ref, pre_reg_doc, mechanism, prior_probability, dsr_cumulative_at_test, validation_result, verdict_date, gates{}, root_cause_if_rejected, linked_papers[], linked_experiments[], linked_reports[]`
- **Experiment:** `title, type, status, hypothesis_ref, trial_id, registry_ref, runner, data_sources[], date_run, verdict, gates_passed, gates_failed, metrics{}, evidence_artifact, root_cause, cost_model`
- **Data:** `title, type, status, category, gold_relevance, cost, update_freq, source, quant_os_integration`
- **Tool:** `title, type, status, category, value, effort, priority_rank, pypi, quant_os_use`
- **Daily:** `title, type, type_daily, papers_read[], hypotheses_advanced[], experiments_run[], open_questions[], edge_leads[]`

---

## 5. Daily Notes Integration

`Daily/YYYY-MM-DD.md` is the **research journal**. Created from `Templates/T_Daily.md`. Each daily note:
- Lists papers read that day (`papers_read:`) → auto-updates the paper's `reading_dates`.
- Logs hypothesis advances and experiment runs (links).
- Captures `open_questions` and `edge_leads` — the raw ore that becomes next-week's hypotheses.
- A **Dataview query** in `Dataview/QUERIES.md` rolls up the last 14 daily notes so you see momentum without opening each.

**Workflow:** open today's daily note first thing. Paste what you read. End of week, scan `open_questions` → lift the best into `Hypotheses/candidates/`.

---

## 6. Dataview Queries

All queries live in `Dataview/QUERIES.md`. They answer the two key questions directly:
- *"Papers we haven't tried"* → papers with `status != applied` AND `rejected_by` empty, sorted by `evidence` + `priority`.
- *"Read / applied / rejected tracking"* → the status/priority pivots per type.

---

## 7. Integration with quant_os

`Integration/Integration_Map.md` is the Rosetta Stone. It maps:
- Each `Hypotheses/` note ↔ its `research/pre_registration/trial_*.md` and `research/hypothesis_registry.json` entry.
- Each `Experiments/` note ↔ its `reports/*.json` / `reports/*.md` evidence artifact.
- Each `Data/` note ↔ the `research/alternative_gold_data_sources.md` section it came from.
- Each `Tooling/` note ↔ the `DEEP_RESEARCH_QUANT_STRATEGIES.md` row it came from.

**The vault never copies numbers.** It stores *judgment* (evidence rating, root cause, prior probability) and *links* to the authoritative artifact in `../research/` or `../reports/`. When a report updates, the vault note's `evidence_artifact` link still resolves — no drift, no duplication.

---

## Quick Start
1. Set Obsidian vault root = `quant_os/vault/`.
2. Install **Dataview** + **Templater** (or core Templates) plugins.
3. Point Templater to `Templates/`.
4. Open `00_MOC/MOC_Hypotheses.md` → start a daily note → read a paper using `T_Paper.md`.
5. When a paper suggests a tradable mechanism, spawn `Hypotheses/candidates/` from `T_Hypothesis.md`, link the paper.
6. When pre-registered, move to `pre-registered/`, run the pipeline, log `Experiments/`, then file under `rejected/` with `root_cause_if_rejected`.
