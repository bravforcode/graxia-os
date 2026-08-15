# Direction I — P1-P3 Pipeline Acceptance Report (2026-08-06)

**Status:** PASS — mining → taxonomy → triage pipeline works end-to-end on the sample fixture
**Evidence:** `research/catalog_i/{catalog_sample,canonical_mechanisms,shortlist}.json` (generated, committed)
**N accounting:** **0 N consumed in P1-P3** — no returns evaluated anywhere in the pipeline (spec §3.2)

## Pipeline run (commands + outputs)

```bash
python scripts/run_mining.py research/catalog_i/catalog_sample.json tests/fixtures/mining_sample.json
# added 7, rejected 0
python scripts/run_taxonomy.py research/catalog_i/catalog_sample.json research/catalog_i/canonical_mechanisms.json
# canonical 6 mechanisms
python scripts/run_triage.py research/catalog_i/canonical_mechanisms.json research/catalog_i/shortlist.json
# shortlist 1 candidates
```

## Per-stage behavior (verified)

| Stage | Input | Output | Notes |
|---|---|---|---|
| Mining (P1) | 7 fixture entries | 7 cataloged, 0 rejected | source_url mandatory enforced; partition tag stamped at ingest |
| Taxonomy (P2) | 7 entries | 6 canonical | **1 excluded: forex4 H1 trend_continuity (USDCAD) — partition CLOSED (Direction H trial 9001 REJECTED, A17)**; grid_martingale flagged `requires_martingale_gate: true` |
| Triage (P3) | 6 canonical | **1 shortlist** | Grid King (martingale, no gate pass) excluded; FX entries killed by cost-viability (EURUSD ~14.17bps RT → 35.7%/yr at 0.5 trades/day > 2% budget); **only XAUUSD D1 trend (0.648bps RT → 1.63%/yr) survives** — cost math working as designed (conservative, A1) |

## Shortlist survivor

`Gold Trend Paper` — trend_following, XAUUSD, D1, evidence_tier=literature, triage.viable=True (annual_cost_pct=1.63 ≤ 2.0 budget).

## Key design validations

1. **Cost-viability kills realistically:** EURUSD retail commissions (~14bps RT) dominate at any trade frequency ≥ 1/2-day — triage correctly eliminates cost-dominated candidates BEFORE any backtest (0 N spent).
2. **Partition enforcement at BOTH layers:** ingest tag + P2 re-check (`check_partition` called in `dedup_to_canonical`) — spec §1.8 "P2 MUST check" satisfied.
3. **Martingale hard-gate gating:** grid_martingale excluded from shortlist until a gate pass is recorded (`_MARTINGALE_GATE_PASSES` — populated at P4).
4. **Evidence-tier ordering:** shortlist sorted literature → myfxbook_verified → practitioner.

## Acceptance tests

`tests/test_p1p3_acceptance.py` — 3/3 pass (artifacts exist; no partition-CLOSED in shortlist).

## Handoff to Plan 3 (P4)

- Screening runner will consume `research/catalog_i/shortlist.json` (currently 1 candidate from sample; real mining target = 2,500+ entries → more survivors after real taxonomy/triage)
- Martingale gate pass registry (`_MARTINGALE_GATE_PASSES`) populated by P4 hard-gate runner
- P4 wiring still blocks on Tier0 Sweep C0 output (guard wiring) per spec P0 item 2
