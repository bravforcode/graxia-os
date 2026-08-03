# Phase 1: Multi-Asset Universe Discovery + Cost-Calibration Pipeline

Status: approved design, pending spec review
Date: 2026-08-03

## Context

`config/tradeable_universe.json` currently lists 3 tradeable symbols (XAUUSD, USOIL,
USDJPY), each gated by `provenance.py`'s `require_cost_calibrated()` against a
hardcoded `COST_CALIBRATED_SYMBOLS` frozenset. This repo has twice fabricated cost
data for symbols outside that set (commit 33b90c31; Trial #1030's bespoke loader) —
the gate exists specifically to stop a third occurrence. Expanding the tradeable
universe today means manually running `market_data/tick_recorder.py`, hand-computing
stats, and hand-editing two JSON files plus the Python frozenset. This design
automates discovery of new broker symbols and their promotion to tradeable status
without weakening the anti-fabrication gate — if anything, tightening it, since the
current 3 symbols don't yet meet their own stated bar (single ~27h window / single
snapshot, not multi-day).

## Approaches considered

1. **Fixed candidate list, manual promotion** (original minimal option). Rejected —
   doesn't scale past 3 symbols and leaves the fabrication-prone manual JSON-editing
   step in place.
2. **Fully automated discovery → measurement → promotion, gate reads JSON live**
   (chosen). Broker enumeration finds new symbols; a daemon measures them against a
   hard statistical bar; promotion/demotion is automatic and reversible; every write
   is provenance-backed. Higher build cost, but removes the manual step that caused
   both prior fabrication incidents.
3. **Automated measurement, manual promotion gate**. Considered as a safer middle
   ground (human reviews before a symbol goes live) but explicitly declined in favor
   of option 2, on the condition that the promotion bar itself is strict enough
   (7 qualifying trading days, full session coverage, re-verification window — see
   below) to not need a human in the loop for the *statistical* decision. Human
   oversight is preserved via the audit log, not a manual approval step.

## 1. Architecture — 3 components

```
[Discovery]  broker symbols_get() → candidate filter → new "candidate" entries
     ↓
[Measurement Daemon]  long-running MT5 tick subscriber, N symbols parallel
     ↓ (per-symbol coverage state, disk-durable)
[Gate]  provenance.py reads tradeable_universe.json live (no more hardcoded frozenset)
```

- **Discovery script**: `symbols_get()` from MT5 → asset-class allowlist filter
  (forex / metals / commodities / indices — no exotics or CFD junk) → sanity bounds
  (spread not absurd, symbol is `symbol_select()`-able) → writes new symbols into
  `tradeable_universe.json` as `status: "candidate"`.
- **Measurement daemon**: extends the existing `market_data/tick_recorder.py`
  pattern — one process, one MT5 connection, subscribes ticks for every
  `candidate`/`measuring` symbol simultaneously, writes rolling per-symbol parquet
  (`data/ticks/{symbol}_{date}.parquet`), classifies each tick
  VALID/STALE/OUT_OF_ORDER/GAP (reuses `TickRecorder`'s existing classification —
  no new tick-quality logic).
- **Gate change**: `provenance.py`'s `require_cost_calibrated()` stops reading the
  `COST_CALIBRATED_SYMBOLS` frozenset and reads `tradeable_universe.json`'s
  `tradeable` list at call time instead. The JSON becomes the true single source of
  truth — daemon writes JSON, gate reads the same JSON. The frozenset and its
  "kept in sync manually" comment are removed.

## 2. Promotion bar

A symbol promotes from `candidate`/`measuring` to `tradeable` only after clearing,
**twice, in two non-overlapping windows**:

- **7 qualifying trading days** — non-consecutive allowed; weekends/holidays are
  excluded from the denominator, not counted as failures.
- **5/5 sessions per qualifying day** (asian / london / london_ny_overlap / ny /
  rollover), with session windows read per-symbol from the broker's `symbol_info`
  trading-session data — not hardcoded from any one symbol's observed hours, since
  USOIL/indices don't share XAUUSD's schedule.
- **≥50,000 VALID ticks per session-day** — VALID per `TickRecorder`'s existing
  classification; a GAP inside a session invalidates that session's coverage claim
  for that day (a flapping connection must not inflate the count with junk).

**Post-promotion re-verification window**: clearing the bar once moves a symbol to
`status: "verifying"`, not `"tradeable"`. It must then clear the identical bar a
second time in a fresh, non-overlapping window before flipping to `"tradeable"`.
This is out-of-sample confirmation of the *cost data itself* — with a broad
asset-class allowlist producing many candidates, a single-pass bar is a screening
threshold with no multiple-comparison correction; a symbol can clear it once on
measurement noise (e.g., one unusually calm week) without having a reliably low
cost. Requiring two independent passes is the cheapest available correction and
mirrors this project's existing insistence on out-of-sample confirmation for
strategies (sacred holdout, walk-forward) — cost data gets the same discipline.

Coverage state (`(symbol, trading_day, session) → covered: bool`, plus which pass
— first or verification — each day counts toward) is persisted to disk next to the
parquet, so daemon restarts, reboots, or weekend gaps never lose day-6 progress.

## 3. Existing 3 symbols (XAUUSD / USOIL / USDJPY)

No grandfathering. On pipeline activation, all three move to `status: "measuring"`
in `tradeable_universe.json` and re-earn tradeable status under the identical bar
(including the re-verification pass) as any newly discovered symbol.

Because this immediately fails `require_cost_calibrated()` for all three — breaking
`validate_dtsmom_strategy.py`, `validate_ram_strategy.py`, the `tsm_*.py` scripts via
`require_cost_calibrated_tsm_asset()`, and `core/trading_loop.py` — the gate function
gains a `mode: "paper" | "live"` parameter, default `"live"` (strictest):

- `mode="paper"`: allowed through for a `measuring`/`verifying` symbol, using its
  last-known cost numbers, with the result tagged with a staleness flag so
  paper P&L reports know the cost basis is provisional.
- `mode="live"`: raises `UncalibratedCostError` until the symbol reaches
  `"tradeable"`.

Callers making live-money decisions must pass `mode="live"` explicitly — the
default protects call sites that forget to specify.

## 4. Auto-promote / auto-demote (reversible)

**Promote**: daemon flips `verifying → tradeable` automatically once the
re-verification pass clears, writing full provenance into `cost_calibration.json`
(`sample_size`, `measurement_window`, `measurement_caveat`,
`status: "FROM_TICKS_MULTIDAY"`). The daemon never emits a status it cannot back
with a named parquet file on disk — no exceptions.

**Demote — drift detection**: reuses `ml/drift_monitor.py`'s PSI computation rather
than introducing a second drift-detection system. `DriftMonitor._calculate_psi()`
is currently a private method operating on ML feature-value distributions; it is
extracted into a shared pure function (e.g. `core/stats/psi.py`) taking two sample
distributions and returning a PSI score, with no dependency on `PredictionRecord`
or model-specific state. `DriftMonitor` (ML feature/accuracy drift, called from
`api/signal_service.py`) and the new cost-drift check both call this one function
on their own domain data — spread-bps samples (baseline window vs. rolling current
window) for cost drift, feature values for ML drift. One statistical primitive,
two call sites, no split-brain.

Threshold: cost-drift PSI exceeding the same `psi_threshold` semantics already
established for feature drift (reuse `DriftMonitor`'s default, 0.25, as the
starting value — not a new arbitrary number) flags the symbol.

**Demote — actions on trigger**:
1. Symbol flips `tradeable → measuring` in `tradeable_universe.json`.
2. Any open live positions on that symbol are flagged via the existing
   `data/kill_switch_state.json` mechanism.
3. **Trial-ledger cross-reference**: every trial in `research/trial_ledger.json` /
   `research/hypothesis_registry*.json` that ran edge-screening against this symbol
   while it was `tradeable` gets an appended note — not a deletion —
   `provenance_invalidated: true` with a pointer to the demote event's audit-log
   entry and the reason (cost basis changed after the trial's GO/NO-GO decision).
   This is the same "keep for the record, mark invalidated" pattern already used
   for Trial #1029/#1030, applied automatically instead of by hand.
4. Entry appended to `state/audit_log.jsonl`: what changed, why (which threshold
   crossed, PSI value), when. The daemon never overwrites a human-authored
   `cost_calibration.json` entry without this audit trail.

## 5. Storage

Raw tick parquet is retained for the active measurement window (first pass +
re-verification pass); after a symbol reaches `tradeable`, raw parquet is pruned
after 30 days and only the aggregate stats in `cost_calibration.json` are kept
long-term. (30 days is a starting number, not load-bearing to the rest of the
design — adjust freely if a different retention policy is preferred.)

## 6. Testing

- Unit: coverage-bar math (qualifying-day counting, per-symbol session-window
  edge cases, VALID-only tick counting, GAP-invalidates-session logic) — pure
  functions, no MT5 dependency.
- Unit: extracted `psi()` function — verify identical output to the current
  `DriftMonitor._calculate_psi()` for ML inputs (no behavior change to existing
  ML drift detection), plus new cases for cost-bps distributions.
- Unit: `provenance.py`'s JSON-read gate, `mode="paper"` vs `mode="live"` split,
  staleness flagging.
- Unit: demote → trial-ledger cross-reference writer (append-only, never deletes).
- Integration: daemon restart mid-measurement resumes coverage state correctly
  (mocked MT5 feed) — a 7+ day wall-clock process WILL see restarts.
- No live-MT5-required test in CI — daemon's MT5 dependency mocked, same pattern
  as the existing `tests/test_mt5_tick_recorder.py`.

## Dependencies / pre-conditions

- LookaheadGuard `get_slice(end_index=...)` bug: verified fixed and re-confirmed
  live this session (`tests/test_walk_forward.py` + `tests/test_lookahead_regression.py`,
  34/34 passed including `test_backtest_guard_prevents_cheating_strategy`). No
  outstanding blocker from this gap for Phase 1.
