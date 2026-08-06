# Direction I Plan 3.1 — P5 Data Infrastructure & Cost Calibration (DRAFT)

> **Status:** DRAFT for review — P4 screening results pending; concrete re-filter targets bind after screening completes.
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Complete the data + cost infrastructure for Direction I: (1) full 23-symbol FROM_TICKS cost calibration, (2) mandatory re-filter of P4 screening survivors at REAL (non-stress) costs, (3) data provenance + TF coverage audit — so survivors enter P6 trials with "edge net of measured costs" (spec §5 P5, A1).

**Architecture:** Reuse the proven forex4 calibration pattern (`scripts/calibrate_forex4_from_ticks.py` + `scripts/backfill_ticks_shortcut.py` — MT5 `copy_ticks_range`). Extend `run_screening.py` with a `--cost-mode base` flag (cost_stress=False) for the mandatory re-filter. Add a calibration registry checker. Universe dependency SATISFIED (C1 landed `cd0f4983` — EURUSD measuring, GBPUSD excluded).

**Tech Stack:** Python 3.11+, MT5 (existing calibration scripts), duckdb/CSV data, `config/cost_calibration.json`, `research/screening_registry.py`.

## Global Constraints

- Trials require FROM_TICKS measured costs — "edge net of an assumption" forbidden (precedent Direction D)
- Re-filter (A1): every P4 survivor re-screened at real costs BEFORE P6; fail at real costs = back to screening pool (same hash, no extra N)
- Symbols without calibration/data = excluded from trials (documented, not default-cost fallback)
- Slippage P90 from fill simulator required for trials; null recorded honestly (never 0.0)
- Writer lock + pre-commit suite + `check_trial_uniqueness.py`; Direction H files untouched
- Engine bug workaround (report `reports/engine_equity_curve_bug_20260806.md`) applied in the re-filter runner; engine-side fix tracked separately

## Current calibration state (verified 2026-08-06)

FROM_TICKS (10): XAUUSD, USDJPY, BTCUSD, EURUSD, GBPUSD, US30, USDCAD, USDCHF, AUDUSD, NZDUSD
Pending (13 target): NAS100 (UNVERIFIED_NO_DATA), OIL (single-snapshot), XAGUSD, XPDUSD, XPTUSD, ETHUSD, US500 + rest of pinned 23-universe (list from `config/tradeable_universe.json` main section AFTER C1)

## File Structure

| File | Responsibility |
|---|---|
| `scripts/calibrate_universe.py` (NEW) | MT5 tick backfill + FROM_TICKS calibration for all pending symbols (loop over `calibrate_forex4_from_ticks.py` pattern) |
| `scripts/run_screening.py` (MODIFY) | Add `--cost-mode {stress,base}` — base = real measured costs (re-filter) |
| `tests/test_calibrate_universe.py` (NEW) | Dry-run/registry-check tests (no MT5 in CI — verify config wiring + status transitions) |
| `reports/direction_i_p5_acceptance_20260806.md` (NEW) | Re-filter results + calibration provenance |

## Task Outline (bind exact numbers after P4 screening completes)

### Task 1: `--cost-mode base` re-filter support
- Extend `run_screening.py`: `--cost-mode` arg → `cost_stress=(mode == "stress")`; re-filter runs with `base`
- Test: CLI accepts both modes; base mode produces identical trade counts with non-zero sharpe (post engine-bug workaround)

### Task 2: Universe pinning + calibration gap list
- Pin the 23-symbol list from `config/tradeable_universe.json` (post-C1)
- Emit `research/catalog_i/calibration_gap.json` — symbols missing FROM_TICKS (script + test)

### Task 3: `scripts/calibrate_universe.py`
- For each gap symbol: `backfill_ticks_shortcut.py` (copy_ticks_range, multi-day window) → `calibrate_forex4_from_ticks.py` pattern → stamp `round_trip_bps_measured` + `status: FROM_TICKS` in `config/cost_calibration.json`
- MT5 connectivity required — run on the machine with MT5; dry-run mode for CI
- Slippage: fill-simulator P90 per symbol; null recorded honestly

### Task 4: Mandatory re-filter of P4 survivors
- Run `run_screening.py --cost-mode base` on survivors only
- Compare vs stress-mode results; survivors at real costs → P6 candidates
- Fail at real costs → status "failed_refilter", back to pool (same hash, no new N)

### Task 5: Acceptance + provenance
- `reports/direction_i_p5_acceptance_20260806.md`: calibration provenance (FROM_TICKS, tick counts, windows), re-filter table, N accounting delta, engine-bug workaround verification

## Dependencies / Blockers

- P4 screening results (in progress, background run)
- MT5 access for tick backfill (proven pattern exists; machine-dependent)
- Sub-project B decisions (EURUSD H4) — only for that candidate's trial path

## Self-Review Notes

- Placeholder: task counts/numbers are structural; symbol list binds in Task 2 (data-dependent by design)
- `--cost-mode` interface matches the runner's existing `cost_stress` config field — no new engine surface
