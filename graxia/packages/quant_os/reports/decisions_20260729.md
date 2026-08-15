# Recorded Decisions — 2026-07-29

Per QUANT_OS_MASTER_REMEDIATION_PLAN_v6.md, Sections 4 and 5. These are user decisions, captured verbatim for future-session continuity — not implementation tasks.

## AI/ML component sign-off (plan Section 4)

**Decision: defer all three.**

| Component | State (audited) | Decision |
|---|---|---|
| `auto_retrain.py` | Real logic, never invoked (no cron/systemd/CI reference) | Deferred — not scheduled |
| `DriftMonitor` | Wired to health endpoint, `record_prediction()` never called | Deferred — stays permanently empty |
| `autonomous/decision_engine.py` | Real LLM wiring, never started by any production entrypoint | Deferred — no production start authorized |

No wiring work was performed on any of the three. Revisit only on explicit future request; `decision_engine.py` specifically requires its own dedicated risk review before ever being started in production, independent of the other two.

## Business reality check (plan Section 5)

**Decision: keep originating new hypotheses** within the existing research framework (technical / macro-cross-asset / cross-sectional / market-neutral), rather than pivoting to replicating a single published strategy exactly, or pausing research to focus solely on infrastructure.

Full rejected-hypothesis history as of this decision:
- Direction A (single-asset technical): 33+ trials, all REJECTED
- Direction B (macro/cross-asset): 4 trials, all REJECTED
- Cross-sectional momentum (Trial #2001-class): REJECTED
- TSM Portfolio: REJECTED (mislabeled 2-asset artifact under jackknife)
- Funding-rate arbitrage: FAIL_RIGOR
- Crypto basis/carry (Trial #6001): REJECTED (p=0.50-0.96 across 8 combinations — mechanism itself not statistically established, not merely insufficient after costs)

No specific next hypothesis was chosen in this session — this decision sets direction only (continue searching, don't pivot to replication or pause). The next research session should pick a specific new candidate, pre-register it in the appropriate hypothesis registry before running (per the F27 "never run-then-register" discipline), and apply the same rigor standard (HAC/Newey-West significance, jackknife, cost-stress, DSR/multiple-testing correction with the TRUE cumulative trial count) that rejected everything tested so far.
